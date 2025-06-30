import csv
from Database import Database

class StatsManager: #Класс для генерации отчетов по вопросам и пользователям в формате CSV

    @staticmethod
    def generate_records_report(diaposone=None): #Генерация CSV-отчета по вопросам за указанный год или за все время.
        db = Database()

        filename = f"records_report_{f"{diaposone[0]}_{diaposone[1]}" if diaposone else 'all'}.csv"
        if diaposone:
            start_date = diaposone[0]
            end_date = diaposone[1]

            records = db.get_records_by_period(start_date, end_date)
        else:
            # Если год не указан - берем все вопросы
            records = db.get_all_records_to_csv()
        if len(records) == 0:
            return False
        
        # CSV-файл
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # столбы
            writer.writerow(['ID_USER', 'Question', 'THEME', 'RECORD_DATE', 'USER_Informativity', 'USER_Usefullness'])
            for q in records:
                writer.writerow([
                    q[0],  # ID
                    q[1],  # текст вопроса
                    q[2],  # тема вопроса
                    q[3],  # дата запроса
                    q[4],  # оценка информативности
                    q[5]   # оценка полезности
                ])
        
        return filename  # Возвращаем имя созданного файла



    @staticmethod
    def generate_users_report():#Генерация CSV-отчета по активности пользователей.
        db = Database()
        filename = "users_report.csv"
        
        # SQL-запрос для получения статистики по пользователям
        db.cursor.execute("""
            SELECT 
                u.id_telegram, 
                COUNT(r.id_record), 
                AVG(r.informativity), 
                AVG(r.usefullness)    
            FROM Users u
            LEFT JOIN Record r ON u.id_user = r.id_user 
            Where r.id_record is not null
            GROUP BY u.id_telegram
        """)
        
        users = db.cursor.fetchall()
        if len(users) == 0:
            return False
        
        # csv файл
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'Telegram ID', 
                'Questions Count', 
                'Avg Informativity', 
                'Avg Usefullness'
            ])
            
            # Данные по каждому пользователю
            for u in users:
                writer.writerow([
                    u[0],  # ID в тг
                    u[1],  # количество вопросов
                    round(u[2], 3),  # средняя информативность
                    round(u[3], 3)   # средняя полезность
                ])
        
        return filename
