import requests
import numpy as np

class LLM():
    def __init__(self):
        pass

    def get_answer_confidence(self, question):
        system_prompt = """Ты интеллектуальный чат-бот, который помогает студентам отвечать на их учебные вопросы.
                Твоя область знаний: программирование на Python, анализ данных, работа с субд и управление проектами.
                Прежде чем ответить, подумай над темой вопроса студента: соответствует ли вопрос твоей области знаний.
                Если нет, то в качестве ответа используй "Вопрос не касается учебной темы" и больше ничего.
                Студент может отправить вопрос с вариантами ответов, в таком случае выбери только правильный ответ из предложенных, не добавляй лишних комментариев."""
        
        url = "http://localhost:8080/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            "logprobs": True
        }
        response = requests.post(url, json=payload, headers=headers)

        choises = response.json()["choices"][0]
        answer = choises["message"]["content"]
        probs = [i['logprob'] for i in choises['logprobs']['content']]
        
        return answer, round(np.exp(np.mean(probs)), 2) * 100
