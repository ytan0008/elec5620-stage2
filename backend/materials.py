"""MaterialLibrary from the Stage 1 class diagram (MaterialLibrary o-- Material)."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.models import Material, MaterialInteraction


def material_dto(item: Material) -> dict:
    return {"id": item.id, "title": item.title, "skill": item.skill, "level": item.level, "description": item.description}


class MaterialLibrary:
    def __init__(self, db: Session):
        self.db = db

    def dismissed_ids(self, user_id: int) -> set[int]:
        """Items the learner marked "Not relevant" (UC10 8a)."""
        return set(self.db.scalars(select(MaterialInteraction.material_id).where(
            MaterialInteraction.user_id == user_id, MaterialInteraction.relevant.is_(False))).all())

    def search(self, weaknesses: list[str], exam: str, exclude: set[int] | None = None) -> list[Material]:
        """Materials for the exam whose skill matches a weakness, weakest first."""
        exclude = exclude or set()
        items = [item for item in self.db.scalars(select(Material).where(Material.exam == exam, Material.skill.in_(weaknesses)))
                 if item.id not in exclude]
        return sorted(items, key=lambda item: weaknesses.index(item.skill))

    def get_starter_materials(self, level: str, exam: str, exclude: set[int] | None = None) -> list[Material]:
        """General materials for a new learner (UC10 2a): their level first, then the rest."""
        exclude = exclude or set()
        items = [item for item in self.db.scalars(select(Material).where(Material.exam == exam)) if item.id not in exclude]
        return sorted(items, key=lambda item: item.level != level)

    def load(self, item_id: int) -> Material | None:
        return self.db.get(Material, item_id)
