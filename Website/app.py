from app import create_app

#creates using the factory in app folder
application = create_app()
if __name__ == '__main__':
    application.run(debug=True, port=5000)