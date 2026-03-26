from sanic import response
from .namespace import page


@page.route('/')
async def handle_request(request):
    return await response.file("dist/index.html")


@page.route('/performance_evaluation')
async def handle_performance_evaluation(request):
    # serve index.html to let the SPA handle the routing
    return await response.file("dist/index.html")
