import logging
import json
import requests
import hashlib
from accounts.models import UserProfile

class SolIncorrectAuthDataException(Exception):
    pass

class SolWorker:
    
    def __init__(self, user):
        self.headers = {'content-type': 'application/json'}
        self.user = user
        self.logger = logging.getLogger(__name__)
        self.sol_login = None
        
    def __fetch_sol_auth_data_from_db(self):
        
        user_profile = UserProfile.objects.filter(user_id=self.user).values('sol_login', 'sol_password')[0]        
        return user_profile['sol_login'], user_profile['sol_password']
    
    def auth(self):
        self.login, password = self.__fetch_sol_auth_data_from_db()
        passw = hashlib.md5(password.encode('utf-8')).hexdigest().upper()
        data = {
            "username": self.login,
            "password": passw,
            "rememberMe": True,
            "companyId": 90,
            "timezoneOffset": -10800000
        }
        
        response = requests.post('http://101.32.207.53:8089/base/api/authenticate', data=json.dumps(data), headers=self.headers)
        try:
            token = response.json()['returnData']['id_token']
        except KeyError:
            if response.json()['returnMsg'] == 'Bad credentials':
                raise SolIncorrectAuthDataException()
        self.headers['Authorization'] = f"Bearer {token}"
        
    def upload_calc_sheet(self, order_no, debit_data, credit_data):
        self.__fetch_sol_auth_data_from_db()
        self.auth()
        json_data = []
        for debit_row in debit_data:
            json_data.append({
                "orderNo": order_no,
                "feeName": int(debit_row.calc_row_service_name),
                "fobCifName": debit_row.calc_row_settlement_procedure,
                "currencyNo": debit_row.calc_row_currency,
                "countUnit": debit_row.calc_row_measure,
                "count": debit_row.calc_row_count,
                "amountSingle": str(debit_row.calc_row_single_amount),
                "payCustomerName": None,
                "recCustomerName": int(debit_row.calc_row_contragent),
                "remark": "",
                "createdBy": self.login 
            })
            
        for credit_row in credit_data:
            json_data.append({
                "orderNo": order_no,
                "feeName": int(credit_row.calc_row_service_name),
                "fobCifName": credit_row.calc_row_settlement_procedure,
                "currencyNo": credit_row.calc_row_currency,
                "countUnit": credit_row.calc_row_measure,
                "count": credit_row.calc_row_count,
                "amountSingle": str(credit_row.calc_row_single_amount),
                "payCustomerName": int(credit_row.calc_row_contragent),
                "recCustomerName": None,
                "remark": "",
                "createdBy": self.login 
            })
        print(*json_data, sep='\n')
        
        response = requests.post('http://101.32.207.53:8089/base/api/saleshipfee/saveBatch', data=json.dumps(json_data), headers=self.headers)
        if response.status_code != 200:            
            self.logger.error(f'Ошибка при загрузке расчетного листа в СОЛ по заявке {order_no}: {response.json(), }')
