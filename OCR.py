import easyocr
import cv2
from difflib import SequenceMatcher

class OCR:

    def __init__(self):
        self.reader =  easyocr.Reader(['ru', 'en'],  gpu=True)


    def DeleteSuspSentence(self, lst):
        # Проверка нижних предложений
        new_lst = []

        # Проверка на наличие большого кол-ва пункт. символов        
        for i in range(len(lst)):
            sent = lst[i]

            if '()' not in sent or '{}' not in sent:
                letterPart = 0
                for char in sent:
                    # Если символ - буква
                    if char.isalpha():
                        letterPart += 1

                if letterPart / len(sent) > 0.6:
                    #Предложение вроде норм
                    new_lst.append(sent)
        
        return new_lst


    def DeleteEmptyStr(self, lst):
        new_list = []
        for i in lst:
            if i != "":
                new_list.append(i)
        return new_list


    def getQuestionIndex(self, list_text):
        quest_index = -1
        for index, sent in enumerate(list_text):
            if sent[-1] == '?' or  sent[-1] == ':' or sent[-1] == '-':
                quest_index = index
                break    
        return quest_index


    def DeleteUpToQuestion(self, list_text):

        # Получение инекса вопроса
        quest_index = self.getQuestionIndex(list_text)
        
        # Все лишние слова находятся сверху вопроса, поэтому ищем индекс самого нижнего из лишних слов
        words = ['Ассесмент', 'ЕДИНАЯ', 'ОБРАЗОВАТЕЛЬНАЯ', 'ПЛАТФОРМА', 'ИННОПОЛИС', 'УНИВЕРСИТЕТА', 'unionepro', 'Вопрос #']
        last_index = 0
        for word in words:
            range_index = len(list_text)
            if quest_index != -1:
                range_index = quest_index

            for i in range(range_index):
                micro_sent = list_text[i]
                for micro_word in micro_sent.split():
                    res = self.Similar(word, micro_word)
                    if res > 0.7:
                        if i > last_index:
                            last_index = i

        # Оставляем текст, не включая лишние слова
        new_text = list_text[last_index + 1:]
        return new_text


    def Similar(self, a, b):
        return SequenceMatcher(None, a, b).ratio()


    def EasyOCR(self, img):
        try:
            result = self.reader.readtext(img)
            txt = []
            for (bbox, text, prob) in result:
                txt.append(text)
            return txt
        except Exception as e:
            print(e)
        return ""


    def Redactor(self, text, text_from_ocr=True):
        
        alphabet = 'йцукенгшщзхъфывапролджэячсмитьбю'
        list_text = self.DeleteEmptyStr(text)

        if text_from_ocr:
            # Удаление лишних найденных элементов, находящихся над вопросом
            list_text = self.DeleteUpToQuestion(list_text)

        # Выделение вопроса
        try:
            # Если есть предложение по типу "Выберите верный ответ", то он располагается всегда под вопросов. Это может помочь с выделением вопроса.
            indexOfChoise = 0
            haveChoise = False
            for index, sent in enumerate(list_text):
                if 'Выберите верный ответ' in sent or 'Выберите верное утверждение' in sent:
                    haveChoise = True
                    indexOfChoise = index
                    break
            
            # Удалив лишние элементы перед вопросом, "складываем" верхние предложения в вопрос.
            question = ""
            if haveChoise:
                quest_index = indexOfChoise-1
                for i in range(0, indexOfChoise):
                    question += list_text[i] + " "
                question = question[:-1]

            else:
                # Проверка, что у вопроса есть ? или :
                quest_index = self.getQuestionIndex(list_text)

                # Создание вопроса
                for i in range(quest_index+1):
                    question += list_text[i] + " "
                question = question[:-1]

        except Exception as e:
            print("Ошибка в выделении вопроса")
            print(e)

        # Варианты ответов
        variants = list_text[indexOfChoise+1:]

        # Удаление странных предложений
        variants = self.DeleteSuspSentence(variants)

        # Удаление лишних слов, также могут являться меткой для удаление всех лишних предложений, стоящих после этих слов
        deleted_words = ['оценку', 'завершить', 'закрыть', 'далее', 'назад']
        min_index_of_deleted_words = 100
        new_variants = []

        # Получение минимального индекса начала лишних слов 
        # + добавляем предложения, не имеющих этих лишних слов в новую переменную 
        for i in range(len(variants)):
            sent = variants[i]
            have_deleted_words = False
            for word in sent.split():
                if word.lower() in deleted_words:
                    have_deleted_words = True
                    if i < min_index_of_deleted_words:
                        min_index_of_deleted_words = i
                    continue
            if not have_deleted_words:
                new_variants.append(sent)

        # Если есть дополнительные лишние предложения, то просто не учитываем их
        if len(new_variants) > min_index_of_deleted_words:
            new_variants = new_variants[:min_index_of_deleted_words]

        # Конкатенация вариантов ответа 
        new_variants2 = []
        for sent in new_variants:
            if sent[0].lower() in alphabet:
                if sent[0] == sent[0].upper():
                    new_variants2.append(sent)
                else:
                    if len(new_variants2) != 0:
                        new_variants2[-1] += " " + sent
                    else:
                        new_variants2.append(sent)
            else:
                if len(new_variants2) != 0:
                    new_variants2[-1] += " " + sent
        return question, new_variants2