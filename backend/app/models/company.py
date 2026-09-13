"""companies 表：公司库（首次启动由 app/seed_data.py 写入 50+ 家互联网公司）。"""

from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    official_site: Mapped[str] = mapped_column(String(500), nullable=True)
    industry: Mapped[str] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    common_positions: Mapped[list] = mapped_column(JSON, default=list)
    logo_url: Mapped[str] = mapped_column(String(1000), nullable=True)
