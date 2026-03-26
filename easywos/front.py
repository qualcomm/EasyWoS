from sanic import Blueprint
from easywos.page.view import page

page = Blueprint.group(page)
