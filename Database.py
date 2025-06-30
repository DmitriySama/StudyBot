import psycopg2
from psycopg2 import sql
import logging
import numpy as np

class Database:
    def __init__(self):
        try:
            # self.conn = psycopg2.connect(
            #     dbname="study_bot_bd",
            #     host="localhost",
            #     user='postgres',
            #     password='Win'
            # )
            self.conn = psycopg2.connect(
                dbname="study_bot",
                host="localhost",
                user='postgres',
                password='Win',
                port=5431
            )
            
            self.cursor = self.conn.cursor()
            logging.info("Успешное подключение к базе данных")
        except Exception as e:
            logging.error(f"Ошибка подключения к базе данных: {e}")
            raise


# Проверка и регистрация пользователя (по id_telegram)
    def check_user_exists(self, telegram_id) -> bool:
        try:
            query = sql.SQL(f"SELECT 1 FROM users WHERE id_telegram = '{telegram_id}'")
            self.cursor.execute(query)
            return bool(self.cursor.fetchone())
        except Exception as e:
            logging.error(f"Ошибка при проверке пользователя: {e}")
            return False


#если пользователя нет в бд, то происходит регистрация
    def register_user(self, telegram_id): 
        try:
            query = sql.SQL("""
                INSERT INTO users (id_telegram, is_curator)
                VALUES (%s, %s)
                RETURNING id_user
            """)
            self.cursor.execute(query, (telegram_id, False))
            self.conn.commit()
            return self.cursor.fetchone()[0]
        
        except Exception as e:
            self.conn.rollback()
            logging.error(f"Ошибка при регистрации пользователя: {e}")
            raise

# Получение id_user
    def get_user_id(self, telegram_id: str) -> int:
        try:
            query = sql.SQL("SELECT id_user FROM Users WHERE id_telegram = %s")
            self.cursor.execute(query, (telegram_id,))
            result = self.cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logging.error(f"Ошибка при получении ID пользователя: {e}")
            return None

#  Проверка на куратора
    def is_curator(self, telegram_id: str) -> bool:
        try:
            query = sql.SQL("SELECT is_curator FROM Users WHERE id_telegram = %s")
            self.cursor.execute(query, (telegram_id,))
            result = self.cursor.fetchone()
            return result[0] if result else False
        except Exception as e:
            logging.error(f"Ошибка при проверке роли куратора: {e}")
            return False


# Назначение куратора
    def set_curator(self, telegram_id, set=True):
        try:
            query = sql.SQL("""
                UPDATE Users 
                SET is_curator = %s 
                WHERE id_telegram = %s
            """)
            self.cursor.execute(query, (set, telegram_id))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logging.error(f"Ошибка при назначении куратора: {e}")
            raise


# Создание начальной записи для нового вопроса
    def create_base_question(self, question_text: str, answer_variants, answer_text: str, theme: str) -> int: #Сохраняет вопрос пользователя в БД
        try:
            query = sql.SQL("""
                INSERT INTO Question 
                (question, answer_variants, answer, informativity, usefullness, evaluate_count, creating_date, theme)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE, %s)
                RETURNING id_question
            """)
            self.cursor.execute(query, (
                question_text, 
                answer_variants,
                answer_text, 
                0, 0, 0,
                theme
            ))
            self.conn.commit()
            return self.cursor.fetchone()[0]
        except Exception as e:
            self.conn.rollback()
            logging.error(f"Ошибка при сохранении вопроса: {e}")
            raise


# Получение всех вопросов для получения схожих вопросов
    def get_questions(self):
        try:
            self.cursor.execute(sql.SQL('select question from question order by id_question'))
            return self.cursor.fetchall()
        except Exception as e:
            logging.error(f"Ошибка при получении вопросов: {e}")
            return []


# Получение рейтинга вопроса и его идентификаторa
    def get_question_rating(self, question):
        try:
            query = sql.SQL("""
                SELECT id_question, informativity, usefullness, evaluate_count 
                FROM Question 
                WHERE question = %s
            """)
            self.cursor.execute(query, (question,))
            return self.cursor.fetchone()
        except Exception as e:
            logging.error(f"Ошибка при получении рейтинга вопроса: {e}")
            return None


# Получение ответа из базы данных
    def get_answer(self, id_question):
        try:
            query = sql.SQL("""
                SELECT answer 
                FROM question 
                WHERE id_question = %s
            """)
            self.cursor.execute(query, (id_question,))
            result = self.cursor.fetchone()
            return result[0]
        except Exception as e:
            logging.error(f"Ошибка при получении ответа: {e}")
            return None


# Получение варинтов ответов у вопроса
    def get_variants(self, id_question):
        try:
            query = sql.SQL("""
                SELECT answer_variants FROM Question 
                WHERE id_question = %s
            """)
            self.cursor.execute(query, (id_question,))
            return self.cursor.fetchone()
        except Exception as e:
            logging.error(f"Ошибка при получении вопроса по ID: {e}")
            return None


#поиск старых ответов
    def get_oldest_answers(self, limit=5):
        try:
            query = sql.SQL("""
                SELECT id_question, question, answer_variants, answer, creating_date, informativity, usefullness 
                FROM Question 
                ORDER BY creating_date ASC 
                LIMIT %s
            """)
            self.cursor.execute(query, (limit,))
            return self.cursor.fetchall()
        except Exception as e:
            logging.error(f"Ошибка при получении старых ответов: {e}")
            return []


# поиск ответов с низкими оценками
    def get_low_rated_questions(self, threshold=3):
        try:
            query = sql.SQL("""
                SELECT id_question, question, answer_variants, answer, creating_date, informativity, usefullness 
                FROM Question 
                WHERE informativity < %s OR usefullness < %s
                ORDER BY informativity + usefullness
                Limit 5
            """)
            self.cursor.execute(query, (threshold, threshold))
            return self.cursor.fetchall()
        except Exception as e:
            logging.error(f"Ошибка при получении вопросов с низкими оценками: {e}")
            return []


# Получение вопросов для отчета
    def get_all_records_to_csv(self):
        query = sql.SQL("""
        SELECT id_user, Question.question, Question.theme, record_date, Record.informativity as user_informativity, Record.usefullness as user_usefullness
        FROM Record left join Question on Record.id_question = Question.id_question
        Order by id_user
        """)
        self.cursor.execute(query)
        return self.cursor.fetchall()


# Получение всех тем за период
    def get_all_themes_by_period(self, start_date, end_date):
        query = sql.SQL("""
        Select id_user, question.theme as theme, Record.informativity, Record.usefullness, from_bd from Record 
        left join question on Record.id_question = Question.id_question
        where record_date between %s and %s 
        """)
        self.cursor.execute(query, (start_date, end_date))
        return self.cursor.fetchall()


# замена ответов
    def replace_old_answer(self, id_question, new_answer):
        try:
            query = sql.SQL("""
                UPDATE Question 
                SET answer = %s, creating_date = NOW(), informativity = 0, usefullness = 0
                WHERE id_question = %s
            """)
            self.cursor.execute(query, (new_answer, id_question))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logging.error(f"Ошибка при замене ответа: {e}")
            raise


# Соотношение источников ответов
    def get_bd_llm_ratio(self, start_date, end_date):
        query = sql.SQL("""
        SELECT 
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE from_bd = True) AS condition_count
        FROM Record
        Where record_date between %s and %s;
        """)
        self.cursor.execute(query, (start_date, end_date))
        return self.cursor.fetchone()


# фильтрация по периодам
    def get_records_by_period(self, start_date, end_date):
        try:
            query = sql.SQL("""
                SELECT id_user, Question.question, Question.theme, record_date, Record.informativity as user_informativity, Record.usefullness as user_usefullness
                FROM Record left join Question on Record.id_question = Question.id_question
                WHERE record_date BETWEEN %s AND %s
                Order by id_user
            """)
            self.cursor.execute(query, (start_date, end_date))
            return self.cursor.fetchall()
        except Exception as e:
            logging.error(f"Ошибка при получении вопросов по периоду: {e}")
            return []


# Обновление нового вопроса
    def update_new_question(self, id_question, informativity, usefullness) -> int:
        try:
            # Запрос на обновление
            query = sql.SQL("""
                Update Question
                set informativity = %s, usefullness = %s, evaluate_count = %s
                where id_question = %s
            """)

            # Обновление вопроса
            self.cursor.execute(query, (
                informativity, 
                usefullness, 
                1, 
                id_question
            ))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logging.error(f"Ошибка при обновлении нового вопроса: {e}")
            raise


# Обновление старого вопроса
    def update_question_grades(self, id_question, informativity, usefullness) -> int:
        try:
            # Получение базовых параметров
            self.cursor.execute(sql.SQL(f"""
                                         select informativity, usefullness, evaluate_count
                                         from Question 
                                         where id_question = {id_question}"""))
            self.conn.commit()
            res = self.cursor.fetchone()
            base_informativity, base_usefullness, base_count = res[0], res[1], res[2]

            # Получение новых параметров
            new_informativity, new_usefullness = self.update_parameters(base_informativity, informativity, base_usefullness, usefullness, base_count)

            # Запрос на обновление
            query = sql.SQL("""
                Update Question
                set informativity = %s, usefullness = %s, evaluate_count = %s
                where id_question = %s
            """)

            # Обновление вопроса
            self.cursor.execute(query, (
                float(new_informativity), 
                float(new_usefullness), 
                base_count+1,
                id_question
            ))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logging.error(f"Ошибка при обновлении оценок вопроса: {e}")
            raise


# Правила обновления оценок старым вопросам
    def update_parameters(self, base_informativity, informativity, base_usefullness, usefullness, base_count):
        # Получение новых параметров
        new_count = base_count + 1
        new_informativity = np.round((base_informativity * base_count + informativity ) / new_count)
        new_usefullness = np.round((base_usefullness * base_count + usefullness ) / new_count)

        return new_informativity, new_usefullness


#Создает запись Record
    def save_rating_in_record(self, user_id, question_id, informativity, usefullness, from_bd):
        try:
            query = sql.SQL("""
                INSERT INTO Record (id_user, id_question, informativity, usefullness, from_bd, record_date)
                VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
            """)
            self.cursor.execute(query, (user_id, question_id, informativity, usefullness, from_bd))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logging.error(f"Ошибка при сохранении оценки: {e}")
            raise
    
    
# Закрытия бд
    def close(self):
        try:
            if hasattr(self, 'cursor') and self.cursor:
                self.cursor.close()
            if hasattr(self, 'conn') and self.conn:
                self.conn.close()
            logging.info("Соединение с базой данных закрыто")
        except Exception as e:
            logging.error(f"Ошибка при закрытии соединения: {e}")
