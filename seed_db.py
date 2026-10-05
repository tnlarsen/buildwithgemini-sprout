"""Seed script to populate Firestore 'plants' collection with initial items."""

from google.cloud import firestore

# Project ID hardcoded as required for Agent Platform compatibility
PROJECT_ID = "qwiklabs-gcp-02-1022f994a1ac"

SEEDED_PLANTS = [
    {
        "id": "monstera-deliciosa",
        "name": "Monstera Deliciosa",
        "species": "Monstera deliciosa",
        "location": "Living Room",
        "watering_interval_days": 7,
        "last_watered_date": "2026-09-29",
        "is_pet_toxic": True,
        "notes": "Prefers bright indirect light. Wipe leaves periodically.",
    },
    {
        "id": "peace-lily",
        "name": "Peace Lily",
        "species": "Spathiphyllum",
        "location": "Bedroom",
        "watering_interval_days": 5,
        "last_watered_date": "2026-09-28",
        "is_pet_toxic": True,
        "notes": "Keep soil slightly moist. Droops when thirsty.",
    },
    {
        "id": "boston-fern",
        "name": "Boston Fern",
        "species": "Nephrolepis exaltata",
        "location": "Bathroom",
        "watering_interval_days": 3,
        "last_watered_date": "2026-10-04",
        "is_pet_toxic": False,
        "notes": "Thrives in high humidity. Mist frequently.",
    },
    {
        "id": "snake-plant",
        "name": "Snake Plant",
        "species": "Sansevieria trifasciata",
        "location": "Office",
        "watering_interval_days": 14,
        "last_watered_date": "2026-09-20",
        "is_pet_toxic": True,
        "notes": "Drought tolerant. Allow soil to dry completely between waterings.",
    },
]


def seed_database():
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection("plants")

    print(f"Seeding Firestore collection 'plants' in project {PROJECT_ID}...")
    for plant in SEEDED_PLANTS:
        doc_id = plant["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(plant)
        print(f"  - Seeded plant: {plant['name']} (ID: {doc_id})")

    print("Firestore database seeded successfully!")


if __name__ == "__main__":
    seed_database()
