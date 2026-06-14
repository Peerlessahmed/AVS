"""
تهيئة قاعدة البيانات — شغّله مرة واحدة
"""
import os, sys

# تأكد من قراءة .env أولاً
from dotenv import load_dotenv
load_dotenv()

from infrastructure import engine
from models import Base  # all core models
import models.prompt_models  # register prompt tables

def init():
    print("🗄️  إنشاء جداول قاعدة البيانات...")
    Base.metadata.create_all(bind=engine)
    print("✅ تم إنشاء جميع الجداول بنجاح!")
    print("\nالجداول المنشأة:")
    for table in Base.metadata.sorted_tables:
        print(f"  • {table.name}")

if __name__ == "__main__":
    init()
