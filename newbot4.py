import logging
import asyncio
import sys
from PIL import Image
import io
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import numpy as np

import aiohttp
from Database import Database
from OCR import OCR
from llm2 import LLM
from similarity import Similarity
from stats_manager import StatsManager

# Константы для состояний ConversationHandler
(
    GETTING_QUESTION, GET_LLM_BD_STAT, SET_CURATOR, DEL_CURATOR, GETTING_PHOTO, GETTING_CHOISE, RATING_ANSWER,
    CURATOR_MENU, VIEW_OLD_ANSWERS, VIEW_LOW_RATED, REPLACE_ANSWER, STATS_MENU,
    GET_DIAPOSONE_STATS, GET_THEME_STATS, GET_USER_STATS
) = range(15)


db = Database()
sim = Similarity()
ocr = OCR()
llm = LLM()
stats_manager = StatsManager()

# Настройка логгера для кураторов
curator_logger = logging.getLogger('curator_actions')
curator_logger.setLevel(logging.INFO)
curator_handler = logging.FileHandler('curator_actions.log', encoding='utf-8')
curator_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
curator_logger.addHandler(curator_handler)

# Настройка логгера для кураторов
bot_logger = logging.getLogger('bot_actions')
bot_logger.setLevel(logging.INFO)
bot_handler = logging.FileHandler('bot.log', encoding='utf-8')
bot_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
bot_logger.addHandler(bot_handler)


# Регистрирует пользователя и приветствует
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    user = update.effective_user
    text = "Используй\n" \
    "\t/question, чтобы задать вопрос в виде текста.\n" \
    "\t/photo, чтобы задать вопрос в виде изображения\n" \
    "\t/rules, чтобы посмотреть правила принимаемых вопросов" 
    
    if not db.check_user_exists(str(user.id)):
        try:
            db.register_user(
                telegram_id=str(user.id)
            )
            await update.message.reply_text(
                f"Привет, {user.first_name}! Добро пожаловать. \n{text}"
            )
        
        except Exception as e:
            await update.message.reply_text(
                "Произошла ошибка при регистрации. Пожалуйста, попробуйте позже."
            )
            logging.error(f"Ошибка регистрации пользователя: {e}")
    else:
        # Проверка на админа
        if(is_admin(user.id)):
            curator_text = f"С возвращением, {user.first_name}!\n" + text
            curator_text += "\n\nФункции куратора:\n" \
            "/curator, чтобы получить основной функционал куратора\n" \
            "/id, чтобы узнать свой telegram_id"
            admin_text = curator_text + "\n\nФункционал администратора:\n" \
            "/set_curator, чтобы добавление куратора\n" \
            "/del_curator, чтобы удалить куратора" 
            
            await update.message.reply_text(admin_text)
            return ConversationHandler.END
        

        # Проверка на куратора
        if(db.is_curator):
            curator_text = f"С возвращением, {user.first_name}!\n" + text
            curator_text += "\n\nФункции куратора:\n" \
            "/curator, чтобы получить основной функционал куратора\n" \
            "/id, чтобы узнать свой telegram_id"
            await update.message.reply_text(curator_text)
            return ConversationHandler.END
        
        
        
    return ConversationHandler.END


def is_admin(id):
    with open('admins.csv', 'r') as admins:
        lines = admins.readlines()
        tg_ids = list(map(lambda x: int(x.split(',')[0]), lines[1:]))
        if id in tg_ids:
            return True
        return False


# Функция выдачи правил
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Правила:\n"
        "1. Бот лучше распознает текст на изображении, если на нем не будет лишней информации.\n\n"
        "2. Бот не умеет распознавать математические формулы, поэтому лучше введите текст.\n\n"
        "3. Шаблон изображений: 1 вопрос и варианты ответов.\n\n"
        "4. Если что-то зависло, попробуйте использовать /cancel"

    )
    return ConversationHandler.END


# Функция получения ID телеграмма
async def id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш id: {update.effective_user.id}")
    return ConversationHandler.END


# Функция ожидания вопроса в виде текста 
async def question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пожалуйста, напишите свой вопрос:\n"
        "Используй /cancel для отмены."
    )
    return GETTING_QUESTION


#обработка текстового вопроса
async def get_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    try:
        question_text = update.message.text.split('\n')
    except:
        await update.message.reply_text("Не обнаружено текста вопроса.")
        bot_logger.info('Не обнаружено текста вопроса')
        return ConversationHandler.END
    
    # Не открытый вопрос
    if len(question_text) > 1:
        question, variants = ocr.Redactor(question_text, False)
        full_text = update.message.text
    else:
        question, variants = update.message.text, []
        full_text = question + "\n"
        for index, var in enumerate(variants):
            full_text += f"{index+1}. {var}"

    sentences = [sent[0] for sent in db.get_questions()]
    questions, similarities, most_similar_idx = sim.similarities(question, sentences)
    most_similar_idx = [i+1 for i in most_similar_idx]
    context.user_data.update({
        'full_text': full_text,
        'question': question,
        'variants': variants,
        'from_bd': False,
        'from_llm': False
    })
    
    await show_similar_questions(update, context, questions, similarities, most_similar_idx)
    return GETTING_CHOISE


# Функция ожидания изображения
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пожалуйста, прикрепите изображение с вопросом:\n"
        "Используй /cancel для отмены."
    )
    return GETTING_PHOTO


# обработка вопроса в виде фото
async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_file.file_path) as response:
                    if response.status == 200:
                        photo_bytes = await response.read()
                        img = Image.open(io.BytesIO(photo_bytes))
                        text = ocr.EasyOCR(img)
                        question, variants = ocr.Redactor(text)

                        await update.message.reply_text(question)
                        vars = ""
                        for var in variants:
                            vars += f"{var}\n"
                        await update.message.reply_text(vars)
                        text = question + "\n"
                        for index, var in enumerate(variants):
                            text += f"{index + 1}. {var}" 
                      
                        sentences = [sent[0] for sent in db.get_questions()]
                        questions, similarities, most_similar_idx = sim.similarities(question, sentences)
                       
                        context.user_data.update({
                            'full_text': question,
                            'question': question,
                            'variants': variants,
                            'from_bd': False,
                            'from_llm': False
                        })
                       
                        await show_similar_questions(update, context, questions, similarities, most_similar_idx)
                        return GETTING_CHOISE
        except:
            await update.message.reply_text("Не обнаружено входное изображение или оно не соответствует шаблону (вопрос + варианты ответов).")
            bot_logger.info('Не обнаружено входное изображение или оно не соответствует шаблону')
            return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")
        bot_logger.info(f'Ошибка {e}')
        return ConversationHandler.END


# Обработка выбора
async def process_choise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choise = update.message.text
    user = update.effective_user
    
    user_id = db.get_user_id(str(user.id))
    context.user_data['user_id'] = user_id

    # Получение ответа от нейросети
    if choise == '0':
        try:
            return await get_answer_by_LLM(update, context)
        
        except Exception as e:
            await update.message.reply_text("Произошла ошибка при получении ответа от нейросети")
            bot_logger.info(f"Ошибка получения ответа от нейросети: {e}")
            return ConversationHandler.END
        
    # Получение ответа из бд
    else:
        choise = int(choise)
        try:
            id_question = context.user_data['id_questions'][choise-1]

            # Получение самого ответа с помощью запроса в бд
            answer = db.get_answer(id_question)

            context.user_data['from_bd'] = True
            context.user_data['id_question'] = id_question
            
            await update.message.reply_text(f"Ответ: {answer}")

        except Exception as e:
            await update.message.reply_text("Произошла ошибка при получении ответа из базы данных")
            bot_logger.info(f"Ошибка получение ответа из базы данных: {e}")
            return ConversationHandler.END

    return await ask_for_rating(update, context)


# Функция создания нового вопроса в базе данных + выдача ответа пользователю
async def get_answer_by_LLM(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        # Генерация ответа от нейросети
        theme = sim.get_theme(context.user_data['question'])
        #confidence, answer = llm.get_answer_confidence(context.user_data['full_text'])
        answer, confidence = llm.get_answer_confidence(context.user_data['full_text'])
        
        context.user_data['from_llm'] = True

        # Выдача ответа пользователю
        await update.message.reply_text(f"Уверенность {confidence}%\n{answer}")

        # Создании начального вида записи нового вопроса
        id_question = db.create_base_question(context.user_data['question'], context.user_data['variants'], answer, theme)
        context.user_data['id_question'] = id_question

        # Запрос оценки ответа
        return await ask_for_rating(update, context)
    except Exception as e:
        await update.message.reply_text("Произошла ошибка при генерации ответа")
        bot_logger.info(f"Ошибка генерации ответа: {e}")
        return ConversationHandler.END


async def ask_for_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: #Запрашивает оценку информативности ответа
    rating_keyboard = [['1', '2', '3', '4', '5']]
    reply_markup = ReplyKeyboardMarkup(
        rating_keyboard, 
        one_time_keyboard=True,
        resize_keyboard=True
    )
    await update.message.reply_text(
        "Пожалуйста, оцените информативность ответа (1-5):",
        reply_markup=reply_markup
    )
    return RATING_ANSWER


# показать похожие вопросы из базы
async def show_similar_questions(update, context, questions, similarities, most_similar_idx):
    await update.message.reply_text(
        "В базе данных нашлись похожие вопросы. \nНапишите номер вопроса, чтобы получить ответ \nили 0 для генерации ответа нейросетью:"
    )
    try:
        # Составление вариантов ответов
        vars = []
        for idx in most_similar_idx:
            variants = db.get_variants(idx)
            if variants == None:
                vars.append('')
            else:
                vars.append(variants[0])
        # Перечисление схожих вопросов
        id_questions = []
        for index, question_from_bd in enumerate(questions):
            id_question, informativity, usefullness, evaluate_count = db.get_question_rating(question_from_bd)
            id_questions.append(id_question)

            q_vars = vars[index]
            vars_text = ""
            if len(q_vars) > 0:
                for var in q_vars:
                    vars_text += f"{var}\n"        
            text = (f"Номер {index+1}. {question_from_bd}\n"  
                    f"Варианты ответов: \n{vars_text}"
                    f"\n============Доп. информация============\n"
                    f"Похожесть на ваш вопрос: {round(similarities[index], 2) * 100}%\n"
                    f"Рейтинг информативности: {informativity}\n"
                    f"Рейтинг полезности: {usefullness}\n"
                    f"Количество оценок: {evaluate_count}\n")
            await update.message.reply_text(text)
        context.user_data['id_questions'] = id_questions
    except Exception as e: 
        await update.message.reply_text('Ошибка получения схожих вопросов из бд')
        bot_logger.info(f'Ошибка предоставления схожих вопросов из бд {e}')


# Назначение куратора ( для админов )
async def set_curator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):  
        await update.message.reply_text("Доступ запрещен")
        return
    await update.message.reply_text("Введите telegram_id нового куратора")
    return SET_CURATOR


# Добавление куратора в базу данных
async def set_curator_part2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    curator_id = update.message.text

    try:    
        # Проверка на существование человека
        if db.check_user_exists(curator_id):
            db.set_curator(curator_id)
            await update.message.reply_text(f"Пользователь {curator_id} назначен куратором")
        else:
            await update.message.reply_text("Человека с таким id нет в базе данных")

    except Exception as e:
        await update.message.reply_text("Не удалось назначить куратора")
        bot_logger.info(f"Ошибка добавления куратора {e}")
    
    return ConversationHandler.END


# Удаление куратора ( для админов )
async def del_curator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):  
        await update.message.reply_text("Доступ запрещен")
        return
    await update.message.reply_text("Введите telegram_id удаляемого куратора")
    return DEL_CURATOR


async def del_curator_part2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    curator_id = update.message.text

    try:    
        # Проверка на существование человека
        if db.check_user_exists(curator_id):
            db.set_curator(curator_id, set=False)
            await update.message.reply_text(f"Пользователь {curator_id} перестал быть куратором")
        else:
            await update.message.reply_text("Человека с таким id нет в базе данных")

    except Exception as e:
        await update.message.reply_text("Не удалось удалить куратора")
        bot_logger.info(f"Ошибка добавления куратора {e}")
    
    return ConversationHandler.END


# меню Куратора
async def curator_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_curator(str(update.effective_user.id)):
        await update.message.reply_text("Доступ запрещен")
        return ConversationHandler.END
    
    keyboard = [
        ['Самые старые ответы', 'Ответы с низкими оценками'],
        ['Заменить ответ', 'Статистика']
    ]
    await update.message.reply_text(
        "Меню куратора:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CURATOR_MENU


# обработка выбора в меню куратора
async def handle_curator_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    curator_logger.info(f"Curator {update.effective_user.id} selected: {choice}")
    
    if choice == 'Самые старые ответы':
        answers = db.get_oldest_answers(limit=5)
        for ans in answers:
            vars= "\n"
            for index, var in enumerate(ans[2]):
                vars += f"{var}\n"
            
            text = (f"ID: {ans[0]}\n\nВопрос: {ans[1]}\nВарианты ответов: {vars}\n"
                   f"Ответ: {ans[3]}\n\nДата: {ans[4]}\n"
                   f"Информативность: {ans[5]}\n"
                   f"Полезность: {ans[6]}")
            await update.message.reply_text(text)
        return await curator_menu(update, context)
    
    elif choice == 'Ответы с низкими оценками':
        answers = db.get_low_rated_questions(threshold=3)
        for ans in answers:
            vars= "\n"
            for index, var in enumerate(ans[2]):
                vars += f"{var}\n"
            
            text = (f"ID: {ans[0]}\n\nВопрос: {ans[1]}\nВарианты ответов: {vars}\n"
                   f"Ответ: {ans[3]}\n\nДата: {ans[4]}\n"
                   f"Информативность: {ans[5]}\n"
                   f"Полезность: {ans[6]}")
            await update.message.reply_text(text)
        return await curator_menu(update, context)
    
    elif choice == 'Заменить ответ':
        await update.message.reply_text(
            "Введите ID вопроса и новый ответ через двоеточие, например:\n"
            "123: Новый ответ"
        )
        return REPLACE_ANSWER
    
    elif choice == 'Статистика':
        keyboard = [
            ['По диапозону', 'По темам'],
            ['По пользователям', 'Общая'],
            ['Соотношение BD/LLM', 'Назад']
        ]
        await update.message.reply_text(
            "Выберите тип статистики:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return STATS_MENU
    
    return CURATOR_MENU


# Обработка меню статистики
async def stats_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    curator_logger.info(f"Curator {update.effective_user.id} selected stats: {choice}")
    
    if choice == 'По диапозону':
        await update.message.reply_text(
            "Введите промежуток в формате dd.mm.yyyy - dd.mm.yyyy для получения статистики:",
            reply_markup=ReplyKeyboardRemove()
        )
        return GET_DIAPOSONE_STATS
    
    elif choice == 'По темам':
        await update.message.reply_text(
            "Введите промежуток времени в формате dd.mm.yyyy - dd.mm.yyyy",
        )
        return GET_THEME_STATS
    
    elif choice == 'По пользователям':
        try:
            filename = stats_manager.generate_users_report()
            if filename == False:
                await update.message.reply_text('Либо студентов нет, либо никто из них еще не задал вопрос')
            else:
                await update.message.reply_document(
                    document=open(filename, 'rb'),
                    caption="Отчет по пользователям"
                )
        except Exception as e:
            await update.message.reply_text(f"Ошибка генерации отчета: {str(e)}")

        keyboard = [
            ['По диапозону', 'По темам'],
            ['По пользователям', 'Общая'],
            ['Соотношение BD/LLM', 'Назад']
        ]   
        await update.message.reply_text(
        "Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return STATS_MENU
    
    elif choice == 'Соотношение BD/LLM':
        await update.message.reply_text("Введите промежуток дат в формате dd.mm.yyyy - dd.mm.yyyy")
        return GET_LLM_BD_STAT

    elif choice == 'Общая':
        try:
            filename = stats_manager.generate_records_report()
            if filename == False:
                await update.message.reply_text("Нет данных для создания отчета")
            else:
                await update.message.reply_document(
                    document=open(filename, 'rb'),
                    caption="Общий отчет по вопросам"
                )
        except Exception as e:
            await update.message.reply_text(f"Ошибка генерации отчета: {str(e)}")
        
        keyboard = [
            ['По диапозону', 'По темам'],
            ['По пользователям', 'Общая'],
            ['Соотношение BD/LLM', 'Назад']
        ]   
        await update.message.reply_text(
        "Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        return STATS_MENU
    
    elif choice == 'Назад':
        keyboard = [
            ['Самые старые ответы', 'Ответы с низкими оценками'],
            ['Заменить ответ', 'Статистика']
        ]
        await update.message.reply_text(
            "Меню куратора:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CURATOR_MENU
    
    return await stats_menu_handler(update, context)


# Получение статистики по темам
async def get_theme_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.split(' - ')
    if len(text) == 1:
        await update.message.reply_text("Введен неверный формат")
        keyboard = [
            ['По диапозону', 'По темам'],
            ['По пользователям', 'Общая'],
            ['Соотношение BD/LLM', 'Назад']
        ]   
        await update.message.reply_text(
        "Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        return STATS_MENU
    
    end_date = text[1]
    start_date = text[0]
    themes = db.get_all_themes_by_period(start_date, end_date)
    if len(themes) == 0:
        await update.message.reply_text('Не нашлось записей за этот промежуток')
        keyboard = [
            ['По диапозону', 'По темам'],
            ['По пользователям', 'Общая'],
            ['Соотношение BD/LLM', 'Назад']
        ]   
        await update.message.reply_text(
        "Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        return STATS_MENU


    # Получение всех тем по отдельности
    data = [theme_record for theme_record in themes if theme_record[1] == 'Анализ данных']
    python = [theme_record for theme_record in themes if theme_record[1] == 'Программирование']
    SUBD = [theme_record for theme_record in themes if theme_record[1] == 'работа с субд']
    projects = [theme_record for theme_record in themes if theme_record[1] == 'Управление проектами']
    other = [theme_record for theme_record in themes if theme_record[1] == 'Другое']
    ignoring = [theme_record for theme_record in themes if theme_record[1] == 'Игнорируемое']

    all_themes = []
    themes_names = []
    if len(data) > 0:
        all_themes.append(data)
        themes_names.append("Анализ данных")
    if len(python) > 0:
        all_themes.append(python)
        themes_names.append("Программирование")
    if len(SUBD) > 0:
        all_themes.append(SUBD)
        themes_names.append("Работа с субд")
    if len(projects) > 0:
        all_themes.append(projects)
        themes_names.append("Управление проектами")
    if len(other) > 0:
        all_themes.append(other)
        themes_names.append("Другое")
    if len(ignoring) > 0:
        all_themes.append(ignoring)
        themes_names.append("Игнорируемое")
    
    # Получение количества вопросов по данной теме
    all_counts = [len(theme) for theme in all_themes]
    
    # Средняя информативность и полезность по темам
    all_informativity = [np.mean([i[2] for i in theme]) for theme in all_themes]
    all_usefullness = [np.mean([i[3] for i in theme]) for theme in all_themes]
    
    # Соотношение BD / LLM
    all_bd_score = []
    for index, theme in enumerate(all_themes):
        bd_count = len([i[4] for i in theme if i[4] == True])
        all_bd_score.append(
            int(round(bd_count / all_counts[index], 2) * 100)
        )

    # Количество студентов, спросивших вопрос по данной теме
    all_unique_users = [len(np.unique([i[0] for i in theme])) for theme in all_themes]


    all_text = ""
    for index, theme_name in enumerate(themes_names):
        all_text += f"======< Тема: {theme_name} >======\n"
        all_text += f"Процент ответов из бд : {all_bd_score[index]}%\n"
        all_text += f"Количество вопросов по этом теме: {all_counts[index]}\n"
        all_text += f"Средняя полезность ответов : {round(all_usefullness[index], 2)}\n"
        all_text += f"Средняя информативность ответов : {round(all_informativity[index], 2)}\n"
        all_text += f"Количество студентов, задавших вопрос по этой теме : {all_unique_users[index]}\n\n"

    await update.message.reply_text(all_text)
    keyboard = [
        ['По диапозону', 'По темам'],
        ['По пользователям', 'Общая'],
        ['Соотношение BD/LLM', 'Назад']
    ]
    await update.message.reply_text(
        "Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return STATS_MENU


# Получение общего соотношения bd / llm
async def get_llm_bd_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.split(' - ')
    if len(text) == 1:
        await update.message.reply_text("Введен неверный формат")
        keyboard = [
            ['По диапозону', 'По темам'],
            ['По пользователям', 'Общая'],
            ['Соотношение BD/LLM', 'Назад']
        ]   
        await update.message.reply_text(
        "Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        return STATS_MENU
    
    end_date = text[1]
    start_date = text[0]
    total_count, bd_count = db.get_bd_llm_ratio(start_date, end_date)
    llm_count = total_count - bd_count
    if llm_count == 0:
        ratio = 100
    else:
        ratio = int((bd_count / total_count) * 100)
    await update.message.reply_text(
        f"Всего вопросов: {total_count}\n"
        f"Количество ответов, полученных из базы знаний: {bd_count}\n"
        f"Количество ответов, полученных из LLM: {llm_count}\n"
        f"Процентное соотношение: {ratio}%")

    keyboard = [
        ['По диапозону', 'По темам'],
        ['По пользователям', 'Общая'],
        ['Соотношение BD/LLM', 'Назад']
    ]
    await update.message.reply_text(
        "Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return STATS_MENU


# Обработка статистики по диапозону
async def handle_diaposone_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['По диапозону', 'По темам'],
        ['По пользователям', 'Общая'],
        ['Соотношение BD/LLM', 'Назад']
    ]
    try:   
        start_date, end_date = update.message.text.split(' - ')
        filename = stats_manager.generate_records_report([start_date, end_date])
        if filename == False:
            await update.message.reply_text(f"Записей за указанный диапозон нет в базе данных")
            
            await update.message.reply_text(
                "Выберите тип статистики:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return STATS_MENU
        await update.message.reply_document(
            document=open(filename, 'rb'),
            caption=f"Отчет по запросам студентов за {start_date} - {end_date}"
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка генерации отчета: {str(e)}")
        bot_logger.info(f"Ошибка генерации отчета: {e}")

    await update.message.reply_text(
        "Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return STATS_MENU


#Обработка замены ответа куратором
async def replace_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        question_id, new_answer = text.split(':', 1)
        db.replace_old_answer(int(question_id.strip()), new_answer.strip())

        curator_logger.info(f"Curator {update.effective_user.id} manually replaced answer for question {question_id}")
        await update.message.reply_text("Ответ успешно обновлен")    
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")
        bot_logger.info(f'Ошибка замены ответа {e}')

    keyboard = [
        ['Самые старые ответы', 'Ответы с низкими оценками'],
        ['Заменить ответ', 'Статистика']
    ]
    await update.message.reply_text(
        "Меню куратора:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CURATOR_MENU


# Обработка отмены
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        'Действие отменено.',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def get_informativity_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: #Получает оценку информативности и запрашивает оценку полезности
    rating = update.message.text
    if rating not in ['1', '2', '3', '4', '5']:
        await update.message.reply_text("Пожалуйста, выберите оценку от 1 до 5:")
        return RATING_ANSWER
    
    context.user_data['informativity'] = int(rating)
    await update.message.reply_text(
        "Теперь оцените полезность ответа (1-5):",
        reply_markup=ReplyKeyboardMarkup(
            [['1', '2', '3', '4', '5']],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return RATING_ANSWER + 1


async def get_usefullness_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: #Получает оценку полезности и сохраняет обе оценки в БД
    rating = update.message.text
    if rating not in ['1', '2', '3', '4', '5']:
        await update.message.reply_text("Пожалуйста, выберите оценку от 1 до 5:")
        return RATING_ANSWER + 1
    
    try:
        # Создание записи в таблицу Record
            db.save_rating_in_record(
                context.user_data['user_id'],
                context.user_data['id_question'],
                context.user_data['informativity'],
                int(rating),
                context.user_data['from_bd']
            )
    except Exception as e:
        bot_logger.info(f"Ошибка создания записи Record {e}")

    try:
        if context.user_data['from_llm'] == True:
            db.update_new_question(context.user_data['id_question'], context.user_data['informativity'], int(rating))
        
        if context.user_data['from_bd'] == True:
            db.update_question_grades(context.user_data['id_question'], context.user_data['informativity'], int(rating))

        await update.message.reply_text(
            "Спасибо за оценку! Если у тебя есть еще вопросы, используй /question или /photo",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        await update.message.reply_text("Произошла ошибка при сохранении оценки")
        bot_logger.info(f"Ошибка сохранения оценки: {e}")
    
    return ConversationHandler.END


def main():
    try:
        application = Application.builder().token("7975279602:AAEftjL_K46t7ttglFNdrS6Koi8QHlelFCk").build()
        
        # Обработчик для обычных пользователей
        user_conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', start),
                CommandHandler('question', question),
                CommandHandler('photo', photo),
                CommandHandler('rules', rules),
                CommandHandler('id', id),
            ],
            states={
                GETTING_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_question)],
                GETTING_PHOTO: [MessageHandler(filters.PHOTO & ~filters.COMMAND, get_photo)],
                GETTING_CHOISE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_choise)],
                RATING_ANSWER: [MessageHandler(filters.TEXT, get_informativity_rating)],
                RATING_ANSWER+1: [MessageHandler(filters.TEXT, get_usefullness_rating)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        # Обработчик для кураторов
        curator_handler = ConversationHandler(
            entry_points=[
                CommandHandler('curator', curator_menu),
                CommandHandler('set_curator', set_curator),
                CommandHandler('del_curator', del_curator),
                ],
            states={
                SET_CURATOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_curator_part2)],
                DEL_CURATOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, del_curator_part2)],
                CURATOR_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_curator_choice)],
                REPLACE_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, replace_answer_handler)],
                STATS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, stats_menu_handler)],
                GET_THEME_STATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_theme_stat)],
                GET_DIAPOSONE_STATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_diaposone_stats)],
                GET_LLM_BD_STAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_llm_bd_stat)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        #application.add_handler(CommandHandler("set_curator", set_curator))
        #application.add_handler(CommandHandler("del_curator", del_curator))
        application.add_handler(user_conv_handler)
        application.add_handler(curator_handler)
        
        logging.info("Бот запущен")
        application.run_polling()
            
    except Exception as e:
        logging.error(f"Ошибка в работе бота: {e}")
    finally:
        db.close()
        logging.info("Бот остановлен")

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
