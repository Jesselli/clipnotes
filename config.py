class Config:
    # TODO Obviously this is not secure
    SECRET_KEY = "tempsecretkey"
    SQLALCHEMY_DATABASE_URI = "sqlite:///snippets.sqlite3"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TMP_DIRECTORY = "./tmp"
    TMP_MAX_SIZE = 100 * 1000 * 1000
