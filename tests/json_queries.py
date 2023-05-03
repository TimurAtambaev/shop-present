"""Модуль с наборами данных для тестовых запросов."""

DEFAULT_IMPORT_ID = 1

IMPORT_CITIZENS = {"citizens": [
    {"citizen_id": 1,
     "town": "Москва",
     "street": "Льва Толстого",
     "building": "16к7стр5",
     "apartment": 7,
     "name": "Иванов Иван Иванович",
     "birth_date": "26.12.1986",
     "gender": "male",
     "relatives": [2]},
    {"citizen_id": 2,
     "town": "Москва",
     "street": "Льва Толстого",
     "building": "16к7стр5",
     "apartment": 7,
     "name": "Иванов Сергей Иванович",
     "birth_date": "01.04.1997",
     "gender": "male",
     "relatives": [1]},
    {"citizen_id": 3,
     "town": "Керчь",
     "street": "Иосифа Бродского",
     "building": "2",
     "apartment": 11,
     "name": "Романова Мария Леонидовна",
     "birth_date": "23.11.1986",
     "gender": "female",
     "relatives": []}]
}

ADD_RELATIONS = {"name": "Иванова Мария Леонидовна",
                 "town": "Москва",
                 "street": "Льва Толстого",
                 "building": "16к7стр5",
                 "apartment": 7,
                 "relatives": [1]
                 }

DEL_RELATIONS = {"relatives": []}

CHANGE_CITIZEN = {"import_id": 1, "citizen_id": 3}
