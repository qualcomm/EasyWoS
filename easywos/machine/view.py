from sanic.views import HTTPMethodView
from sanic_ext import openapi
from sanic_ext.extensions.openapi.definitions import RequestBody
from sanic_jwt.decorators import protected

from helper import machine_helper
from .profile import MachineProfile, UpdateMachineProfile
from .namespace import machine


class MachineView(HTTPMethodView):
    decorators = [protected()]

    @openapi.parameter("id", int, required=False)
    @openapi.parameter("name", str, required=False)
    @openapi.parameter("page_num", int, required=False)
    @openapi.parameter("page_size", int, required=False)
    async def get(self, request):
        id = request.args.get('id')
        name = request.args.get('name')
        page_num = int(request.args.get('page_num', 1))
        page_size = int(request.args.get('page_size', 20))
        result = await machine_helper.list_machine(page_num=page_num, page_size=page_size, id=id, name=name)
        return result

    @openapi.body(RequestBody(MachineProfile, required=True))
    async def post(self, request):
        data = request.json

        name = data.get('name')
        host = data.get('host')
        username = data.get('username')
        password = data.get('password')
        port = data.get('port')
        description = data.get('description')
        res = await machine_helper.add_machine(
            name=name,
            host=host,
            username=username,
            password=password,
            port=port,
            description=description
        )

        return res

    @openapi.parameter("id", int, required=True)
    @openapi.body(RequestBody(UpdateMachineProfile))
    async def put(self, request):
        id = request.args.get('id')
        data = request.json

        status = data.get('status')
        username = data.get('username')
        password = data.get('password')
        port = data.get('port')
        description = data.get('description')
        res = await machine_helper.update_machine(
            id=id, status=status, username=username, password=password, port=port,
            description=description
        )
        return res

    @openapi.parameter("id", int, required=True)
    async def delete(self, request):
        id = request.args.get('id')
        result = await machine_helper.delete_machine(id=id)
        return result


class MachineVerifyView(HTTPMethodView):
    async def post(self, request, id):
        res = await machine_helper.verify_machine(
            id=id
        )

        return res


machine.add_route(MachineVerifyView.as_view(), "/verfiy/<id>")
machine.add_route(MachineView.as_view(), "/")
