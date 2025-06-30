from sentence_transformers import SentenceTransformer, util
from joblib import load

class Similarity():
    def __init__(self):
        self.model = SentenceTransformer("./models/embedder_model") 
        self.classificator = load('./models/classificator.joblib')


    def get_theme(self, question):
        quest = self.model.encode([question], convert_to_numpy=True)
        predicted_class = self.classificator.predict(quest)[0]
        return predicted_class


    def similarities(self, entry_question, sentences):
        database_embeddings = self.model.encode(sentences, convert_to_tensor=True)
        question_embedding = self.model.encode(entry_question, convert_to_tensor=True)

        cosine_scores = util.cos_sim(question_embedding, database_embeddings)[0]
        most_similar_idx = cosine_scores.argsort()[-3:].tolist()[::-1]
        
        similar_questions = []
        similarity_scores = []
        for i in range(len(most_similar_idx)):
            idx = most_similar_idx[i]
            cos_score = round(float(cosine_scores[idx]), 2)
            if cos_score > 0.6:
                similar_questions.append(sentences[idx])
                similarity_scores.append(cos_score)

        return similar_questions, similarity_scores, most_similar_idx