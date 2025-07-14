from flask import Blueprint

users = Blueprint('users', __name__)

@users.route('/example')
def example():
    return "This is an example route!"
