import pandas as pd
from sqlalchemy import create_engine

# Database connection
DATABASE_URL = "postgresql://username:password@localhost:5432/your_database"

engine = create_engine(DATABASE_URL)

# SQL query
query = """
SELECT *
FROM users;
"""

# DB dan data olish
df = pd.read_sql(query, engine)

# Excelga yozish
df.to_excel("users_export.xlsx", index=False)

print("Excel fayl yaratildi: users_export.xlsx")