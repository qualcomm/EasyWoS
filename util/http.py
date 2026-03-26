from sanic.response import json as sanic_json


def rsp(code=200, message='success', data=None):
    response = dict(
        code=code,
        message=message,
        data=data
    )
    return sanic_json(response, ensure_ascii=False)
