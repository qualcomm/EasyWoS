"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
import os
import aiofiles
from typing import Union
from models.user import User
from util.http import rsp


async def list_user(page_num, page_size, id=None, username=None):
    """

    :return:
    """

    condition = dict()
    if id:
        condition['id'] = id
    if username:
        condition['username'] = username
    columns = [
        'username', 'status'
    ]
    users = await User.query_page(page_num=page_num, page_size=page_size, condition=condition, columns=columns)
    return rsp(data=users)


async def create_user(username, password) -> rsp:
    if not username:
        return rsp(code=422, message='Username can\'t be empty')
    if not password:
        return rsp(code=422, message='Password can\'t be empty')
    user = User(
        username=username
    )
    user.set_password(password=password)
    user.status = True
    new_user, message, http_code = await User.save(user)

    if not new_user:
        return rsp(code=http_code, message=message)
    columns = [
        'username', 'status'
    ]
    response_date = {
        'user': new_user.serialize(columns=columns)
    }
    return rsp(code=http_code, message=message, data=response_date)


async def update_user(id, status=None, password=None) -> rsp:
    users = await User.query(User.id == id)
    if not users:
        return rsp(code=400, message=f'User {id} doesn\'t exist')
    user = users[0]
    if status is not None:
        if user.username == 'admin':
            return rsp(code=422, message='Admin\'s status can\'t be modified')
        user.status = status
    if password:
        user.set_password(password=password)
    await user.update()
    return rsp(code=200, message=f'Update User {id} success')


async def find_user_exists(username) -> Union[User, None]:
    users = await User().query(User.username == username)
    return users[-1] if len(users) > 0 else None


async def create_init_user():
    init_user = await find_user_exists('admin')
    if not init_user:
        user = User(
            username='admin'
        )
        path = os.path.join(os.getcwd(), 'init_user')
        async with aiofiles.open(path, 'r') as f:
            password = await f.read()
        user.set_password(password=password)
        user.status = True
        await User.save(user)

# def delete_user(id) -> int:
#     """

#     :return:
#     """
#     user = User.query.filter(User.id == id).first()
#     db.session.delete(user)
#     db.session.commit()
#     return id


# def login(username, password) -> int:
#     """

#     :return:
#     """
#     user = User(
#         username=username
#     )
#     user = User.query.filter(User.username == username).first()
#     if not user:
#         return None
#     if not user.check_password(password):
#         return None
#     access_token = create_access_token(identity=user.id)
#     return access_token


# def logout() -> int:
#     """

#     :return:
#     """
#     response = jsonify({"msg": "logout successful"})
#     unset_jwt_cookies(response)
#     return response


async def create_or_get_qualcomm_user(username) -> rsp:
    if not username:
        return rsp(code=422, message='Username can\'t be empty')

    users = await User.query(User.username == username)
    if users:
        user = users[0]
        if not user.status:
            return rsp(code=403, message='User unavailable')
    else:
        user = User(
            username=username
        )
        # Set a random password or a specific one for Qualcomm users
        # Since they login via SSO, this password won't be used normally
        user.set_password(password="Qualcomm_SSO_User_Pwd_" + username)
        user.status = True
        user, message, http_code = await User.save(user)

        if not user:
            return rsp(code=http_code, message=message)

    columns = [
        'username', 'status', 'id'
    ]
    response_data = {
        'user': user.serialize(columns=columns)
    }
    return rsp(data=response_data)

