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
    
    def __authorization(self):
        self.sol_login, password = self.__fetch_sol_auth_data_from_db()
        passw = hashlib.md5(password.encode('utf-8')).hexdigest().upper()
        data = {
            "username": self.sol_login,
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
    
    def auth(self):
        if not "Authorization" in self.headers:
            self.__fetch_sol_auth_data_from_db()
            self.__authorization()
            
    def upload_calc_rows(self, json_data, rows_ids):
        calc_sheet_ids = {}
        self.auth()
        for i in range(len(json_data)):
            try:
                if json_data[i]["createdBy"] == '':
                    json_data[i]["createdBy"] = self.sol_login
            except KeyError:
                pass
        
        response = requests.post('http://101.32.207.53:8089/base/api/saleshipfee/saveBatch', data=json.dumps(json_data), headers=self.headers, timeout=360)
        if response.status_code == 200 and response.json()['returnCode'] == 200:
            for return_data in response.json()['returnData']:
                index, real_id = return_data.values()               
                calc_sheet_ids[rows_ids[index]] = real_id
        return response.status_code, response.json(), calc_sheet_ids