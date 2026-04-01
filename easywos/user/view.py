"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
import base64
import urllib.request
import urllib.error
import ssl
import json
from sanic.views import HTTPMethodView
from sanic.response import json as sanic_json
from sanic_ext import openapi
from sanic_ext.extensions.openapi.definitions import RequestBody
from sanic_jwt.decorators import protected
from helper import user_helper
from .profile import UserProfile, UpdateUserProfile
from .namespace import user


class UserView(HTTPMethodView):
    decorators = [protected()]

    @openapi.parameter("id", int, required=False)
    @openapi.parameter("username", str, required=False)
    @openapi.parameter("page_num", int, required=False)
    @openapi.parameter("page_size", int, required=False)
    async def get(self, request):
        page_num = int(request.args.get('page_num', 1))
        page_size = int(request.args.get('page_size', 20))

        id = request.args.get('id')
        username = request.args.get('username')
        result = await user_helper.list_user(page_num=page_num, page_size=page_size, id=id, username=username)
        return result

    @openapi.body(RequestBody(UserProfile, required=True))
    async def post(self, request):
        data = request.json
        username = data.get('username')
        password = data.get('password')
        res = await user_helper.create_user(
            username=username,
            password=password,
        )
        return res


class UserViewById(HTTPMethodView):
    @openapi.body(RequestBody(UpdateUserProfile))
    async def put(self, request, id):
        data = request.json
        password = data.get('password')
        status = data.get('status')
        res = await user_helper.update_user(
            id=id,
            password=password,
            status=status
        )
        return res

    async def delete(self, request, id):
        res = await user_helper.update_user(
            id=id,
            status=False
        )
        return res


class QualcommLoginView(HTTPMethodView):
    async def post(self, request):
        username = request.json.get('username')
        password = request.json.get('password')
        
        if not username or not password:
            return sanic_json({'message': 'Username and password are required'}, status=400)

        # Proxy authentication request to Qualcomm
        auth_str = f"{username}:{password}"
        auth_bytes = auth_str.encode('ascii')
        base64_bytes = base64.b64encode(auth_bytes)
        base64_auth = base64_bytes.decode('ascii')

        url = "https://sm-sts.qualcomm.com/smapi/rest/createsmsession?hostname=qclogin.qualcomm.com"
        headers = {
            "Authorization": f"Basic {base64_auth}"
        }
        
        try:
            req = urllib.request.Request(url, headers=headers)
            # bypass ssl verification
            ctx = ssl._create_unverified_context()
            
            with urllib.request.urlopen(req, context=ctx) as response:
                if response.status != 200:
                    return sanic_json({'exception': 'Qualcomm authentication failed'}, status=401)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return sanic_json({'exception': 'login.error.qualcomm'}, status=401)
            return sanic_json({'exception': f'Qualcomm login failed: {e.reason}'}, status=e.code)
        except Exception as e:
             return sanic_json({'exception': f'Authentication error: {str(e)}'}, status=401)

        res = await user_helper.create_or_get_qualcomm_user(username)
        res_body = json.loads(res.body)
        
        if res_body.get('code') != 200:
            return sanic_json(res_body, status=res_body.get('code'))

        user_obj = res_body.get('data', {}).get('user')
        user_instance = await user_helper.find_user_exists(username)

        # Generate token using sanic-jwt
        # Try to get auth instance from app.ctx (Sanic 21.3+) or fallback to Utils
        if hasattr(request.app, 'ctx') and hasattr(request.app.ctx, 'auth'):
            access_token = await request.app.ctx.auth.generate_access_token(user_instance)
        else:
            from sanic_jwt import Utils
            utils = Utils(request.app)
            access_token = await utils.get_access_token(user_instance)

        return sanic_json({
            "access_token": access_token,
            "user": user_obj
        })


user.add_route(UserView.as_view(), "/")
user.add_route(UserViewById.as_view(), "/<id>")
user.add_route(QualcommLoginView.as_view(), "/qualcomm_login")


@user.listener('before_server_start')
async def init_user(user, loop):
    await user_helper.create_init_user()
