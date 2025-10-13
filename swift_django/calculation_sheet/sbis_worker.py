import logging
import json
import requests
from accounts.models import UserProfile

class SbisWorker:
    
    def __init__(self, user):
        self.headers = {'Content-Type': 'application/json-rpc;charset=utf-8'}
        self.url = 'https://online.sbis.ru/service/?srv=1'
        self.user = user
        self.user_fio = []
        self.logger = logging.getLogger(__name__)
        
        
    def __fetch_sbis_auth_data_from_db(self):
        """ Получаем данные авторизации для Сбис """

        user_profile = UserProfile.objects.filter(user_id=self.user).values('sbis_login', 'sbis_password')[0]        
        return user_profile['sbis_login'], user_profile['sbis_password']

    def auth(self):
        """ Логинимся в СБИСе """
        
        login, password = self.__fetch_sbis_auth_data_from_db()
        data = {
            'jsonrpc': '2.0',
            'method': 'СБИС.Аутентифицировать',
            'params': {
                'Логин': login,
                'Пароль': password
            },
            'id': 1
        }
        response = requests.post(f'https://online.sbis.ru/auth/service/', data=json.dumps(data), headers=self.headers, timeout=60)
        if response.status_code == 200:
            self.headers['X-SBISSessionID'] = response.json()['result']        
        else:           
            self.logger.error(f"Не получилось авторизоваться в СБИС: {response.status_code}, {response.json()['error']['message']}")
            response.raise_for_status()
            
    def get_user_fio(self):
        data = {
            "jsonrpc": "2.0",
            "method": "СБИС.ИнформацияОТекущемПользователе",
            "params": {
                "Параметр": {
                }
            },
            "id": 0
        }
        
        response = requests.post(url=self.url, data=json.dumps(data), headers=self.headers, timeout=60)
        if response.status_code == 200:
            user = response.json()['result']['Пользователь']
            self.user_fio = [user['Фамилия'], user['Имя'], user['Отчество']]
        else:
            self.logger.error(f"Не удалось получить ФИО пользователя: {response.status_code}, {response.json()['error']['message']}")
            response.raise_for_status()
            
    def create_approval_for_calc_list(self, order_no, pdf):
        
        self.auth()
        self.get_user_fio()
        
        data = {
            "jsonrpc": "2.0",
            "method": "СБИС.ЗаписатьДокумент",
            "params": {
                "Документ": {
                    "Тип": "СлужЗап",
                    "Регламент": {
                        "Идентификатор": "b682c681-869d-4aa9-8aa8-28678c4af097",
                    },
                    "НашаОрганизация": {
                        "СвЮЛ": {
                            "ИНН": "9705052741",
                            "КПП": "772601001",
                        }
                    },
                    "Ответственный": {
                        "Фамилия": self.user_fio[0],
                        "Имя": self.user_fio[1],
                        "Отчество": self.user_fio[2]
                    },
                    "Автор": {
                        "Фамилия": self.user_fio[0],
                        "Имя": self.user_fio[1],
                        "Отчество": self.user_fio[2]
                    },
                    "Вложение": [
                        {
                            "Файл": {    
                                    "Имя": f"{order_no}.pdf",                        
                                    "ДвоичныеДанные": f'{pdf}'
                                }
                        }
                    ]
                }
            },
            "id": 0
        }
        
        response = requests.post(url=self.url, data=json.dumps(data), headers=self.headers, timeout=60)
        if response.status_code == 200:
            sbis_href = response.json()['result']['СсылкаДляНашаОрганизация']
            sbis_doc_id = response.json()['result']['Идентификатор']
            
            data = {
                "jsonrpc": "2.0",
                "method": "СБИС.ВыполнитьДействие",
                "params": {
                    "Документ": {
                        "Идентификатор": sbis_doc_id,
                        "Этап": {
                            "Название": "Выполнение"
                        }
                    }
                },
                "id": 2
            }
            response = requests.post(url=self.url, data=json.dumps(data), headers=self.headers, timeout=60)
            if response.status_code == 200:           
                return sbis_href, sbis_doc_id
            else:
                self.logger.error(f"Не удалось создать задачу на согласование расчетного листа: {response.status_code}, {response.json()['error']['message']}")
                response.raise_for_status()
        else:
            self.logger.error(f"Не удалось создать задачу на согласование расчетного листа: {response.status_code}, {response.json()['error']['message']}")
            response.raise_for_status()