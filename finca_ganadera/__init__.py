# Habilita PyMySQL como reemplazo de MySQLdb
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except Exception:
    pass
