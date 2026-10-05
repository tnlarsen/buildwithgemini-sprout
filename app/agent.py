# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

from dotenv import load_dotenv
from google import genai
from google.cloud import firestore
from google.cloud import storage

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.load_memory_tool import load_memory_tool
from google.adk.tools.preload_memory_tool import preload_memory_tool
from google.genai import types

from .a2ui_utils import a2ui_callback

# Load local environment variables from .env if present
load_dotenv()

# Hardcoded GCP Project ID and Bucket Name for Agent Platform compatibility
PROJECT_ID = "qwiklabs-gcp-02-1022f994a1ac"
BUCKET_NAME = "sprout-plant-care-qwiklabs-gcp-02-1022f994a1ac"


def _get_agent_engine_resource_name() -> Optional[str]:
    """Reads the remote Agent Engine resource ID from deployment_metadata.json if available."""
    candidate_paths = [
        os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json"),
        os.path.join(os.path.dirname(__file__), "deployment_metadata.json"),
        "deployment_metadata.json",
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    remote_id = data.get("remote_agent_runtime_id")
                    if remote_id:
                        return remote_id
            except Exception:
                pass
    return None


def _get_memory_service() -> Optional[VertexAiMemoryBankService]:
    """Initializes VertexAiMemoryBankService using the Agent Engine ID from deployment_metadata.json."""
    remote_id = _get_agent_engine_resource_name()
    if remote_id:
        agent_engine_id = remote_id.split("/")[-1]
        try:
            return VertexAiMemoryBankService(
                project=PROJECT_ID,
                location="us-east1",
                agent_engine_id=agent_engine_id,
            )
        except Exception as e:
            print(f"Notice: Could not initialize VertexAiMemoryBankService: {e}")
    return None


def _get_firestore_db() -> firestore.Client:
    """Returns a Firestore client configured with the hardcoded project ID."""
    return firestore.Client(project=PROJECT_ID)


def list_plants() -> List[Dict[str, Any]]:
    """Retrieves all tracked plants and their watering status from Firestore.

    Returns:
        A list of plant dictionaries containing plant details, days since last watered,
        image URL (if uploaded), and watering status.
    """
    db = _get_firestore_db()
    docs = db.collection("plants").stream()
    today = datetime.date.today()
    plants = []

    for doc in docs:
        data = doc.to_dict()
        last_watered_str = data.get("last_watered_date", "")
        days_since_watered = None
        status = "Unknown"

        if last_watered_str:
            try:
                last_watered = datetime.datetime.strptime(last_watered_str, "%Y-%m-%d").date()
                days_since_watered = (today - last_watered).days
                interval = data.get("watering_interval_days", 7)
                if days_since_watered > interval:
                    status = "Overdue"
                elif days_since_watered == interval:
                    status = "Water Today"
                else:
                    status = "OK"
            except ValueError:
                pass

        data["days_since_watered"] = days_since_watered
        data["status"] = status
        plants.append(data)

    return plants


def add_plant(
    name: str,
    species: str,
    location: str,
    watering_interval_days: int,
    is_pet_toxic: bool = False,
    notes: str = "",
) -> str:
    """Adds a new plant to the Firestore database.

    Args:
        name: Name or nickname given to the plant (e.g., 'Monstera').
        species: Botanical or common species name (e.g., 'Monstera deliciosa').
        location: Where the plant is kept (e.g., 'Living Room').
        watering_interval_days: Number of days between required waterings.
        is_pet_toxic: True if the plant is toxic to pets (cats/dogs).
        notes: Care tips or location notes.

    Returns:
        A confirmation message indicating the plant was added.
    """
    db = _get_firestore_db()
    doc_id = name.lower().replace(" ", "-")
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    plant_data = {
        "id": doc_id,
        "name": name,
        "species": species,
        "location": location,
        "watering_interval_days": watering_interval_days,
        "last_watered_date": today_str,
        "is_pet_toxic": is_pet_toxic,
        "notes": notes,
    }

    db.collection("plants").document(doc_id).set(plant_data)
    warning = " ⚠️ Note: This plant is toxic to pets!" if is_pet_toxic else ""
    return f"Successfully added '{name}' ({species}) to {location} with a {watering_interval_days}-day watering cycle.{warning}"


def update_plant(
    plant_name_or_id: str,
    name: Optional[str] = None,
    species: Optional[str] = None,
    location: Optional[str] = None,
    watering_interval_days: Optional[int] = None,
    last_watered_date: Optional[str] = None,
    is_pet_toxic: Optional[bool] = None,
    notes: Optional[str] = None,
) -> str:
    """Updates one or more attributes of an existing plant in Firestore.

    Args:
        plant_name_or_id: The name or ID of the plant to update (e.g. 'Monstera' or 'monstera-deliciosa').
        name: New nickname or display name for the plant.
        species: New species name.
        location: New location in the home (e.g., 'Patio', 'Sunroom').
        watering_interval_days: New watering frequency in days.
        last_watered_date: Updated last watered date (YYYY-MM-DD).
        is_pet_toxic: Updated pet toxicity status (True/False).
        notes: Updated care notes or observations.

    Returns:
        A status message confirming which fields were updated.
    """
    db = _get_firestore_db()
    collection_ref = db.collection("plants")

    update_fields = {}
    if name is not None:
        update_fields["name"] = name
    if species is not None:
        update_fields["species"] = species
    if location is not None:
        update_fields["location"] = location
    if watering_interval_days is not None:
        update_fields["watering_interval_days"] = watering_interval_days
    if last_watered_date is not None:
        update_fields["last_watered_date"] = last_watered_date
    if is_pet_toxic is not None:
        update_fields["is_pet_toxic"] = is_pet_toxic
    if notes is not None:
        update_fields["notes"] = notes

    if not update_fields:
        return "No attributes were provided to update."

    # Try direct ID match
    doc_id = plant_name_or_id.lower().replace(" ", "-")
    doc_ref = collection_ref.document(doc_id)

    if doc_ref.get().exists:
        doc_ref.update(update_fields)
        updated_keys = ", ".join(update_fields.keys())
        return f"Successfully updated fields [{updated_keys}] for plant '{plant_name_or_id}'."

    # Search by name field
    docs = collection_ref.stream()
    for d in docs:
        data = d.to_dict()
        if data.get("name", "").lower() == plant_name_or_id.lower() or plant_name_or_id.lower() in data.get("name", "").lower():
            d.reference.update(update_fields)
            updated_keys = ", ".join(update_fields.keys())
            return f"Successfully updated fields [{updated_keys}] for plant '{data.get('name')}'."

    return f"Plant matching '{plant_name_or_id}' was not found in your inventory."


def water_plant(plant_name_or_id: str) -> str:
    """Records that a plant was watered today in Firestore.

    Args:
        plant_name_or_id: The name or ID of the plant to update (e.g. 'Monstera' or 'monstera-deliciosa').

    Returns:
        A status message confirming the update.
    """
    db = _get_firestore_db()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    collection_ref = db.collection("plants")

    # Try direct ID match
    doc_id = plant_name_or_id.lower().replace(" ", "-")
    doc_ref = collection_ref.document(doc_id)
    doc = doc_ref.get()

    if doc.exists:
        doc_ref.update({"last_watered_date": today_str})
        plant_name = doc.to_dict().get("name", plant_name_or_id)
        return f"Updated '{plant_name}'! Last watered date recorded as {today_str}."

    # Search by name field
    docs = collection_ref.stream()
    for d in docs:
        data = d.to_dict()
        if data.get("name", "").lower() == plant_name_or_id.lower() or plant_name_or_id.lower() in data.get("name", "").lower():
            d.reference.update({"last_watered_date": today_str})
            return f"Updated '{data.get('name')}'! Last watered date recorded as {today_str}."

    return f"Plant matching '{plant_name_or_id}' was not found in your inventory."


def check_reminders() -> str:
    """Checks Firestore for any plants that are due or overdue for watering.

    Returns:
        A summary string listing plants that need water.
    """
    plants = list_plants()
    due_plants = [p for p in plants if p.get("status") in ("Overdue", "Water Today")]

    if not due_plants:
        return "All your plants are well-watered! No watering reminders at this time."

    summary = ["🌱 Plants needing water:"]
    for p in due_plants:
        days = p.get("days_since_watered", "?")
        interval = p.get("watering_interval_days", "?")
        summary.append(f"  • {p.get('name')} ({p.get('location')}): {days} days since last watered (interval: {interval} days) - Status: {p.get('status')}")

    return "\n".join(summary)


def upload_plant_photo(plant_name_or_id: str, file_path: str) -> str:
    """Uploads a plant photo to Google Cloud Storage and attaches the public image URL to the plant's Firestore profile.

    Args:
        plant_name_or_id: The name or ID of the plant (e.g., 'Monstera' or 'monstera-deliciosa').
        file_path: The local absolute or relative file path to the plant image.

    Returns:
        A confirmation message with the public Cloud Storage URL.
    """
    if not os.path.exists(file_path):
        return f"Error: Local file '{file_path}' does not exist."

    filename = os.path.basename(file_path)
    destination_blob_name = f"plant_photos/{plant_name_or_id.lower().replace(' ', '-')}_{filename}"

    try:
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(file_path)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{destination_blob_name}"

        # Update Firestore
        db = _get_firestore_db()
        collection_ref = db.collection("plants")
        doc_id = plant_name_or_id.lower().replace(" ", "-")
        doc_ref = collection_ref.document(doc_id)

        if doc_ref.get().exists:
            doc_ref.update({"image_url": public_url})
        else:
            # Search by name
            docs = collection_ref.stream()
            for d in docs:
                data = d.to_dict()
                if data.get("name", "").lower() == plant_name_or_id.lower() or plant_name_or_id.lower() in data.get("name", "").lower():
                    d.reference.update({"image_url": public_url})
                    break

        return f"Successfully uploaded photo for '{plant_name_or_id}'! Public image URL: {public_url}"
    except Exception as e:
        return f"Failed to upload photo: {e}"


def fetch_weather_care_advisory(location: str) -> str:
    """Fetches real-time weather and humidity data for a location to generate environmental care advice for plants.

    Args:
        location: City or region name (e.g. 'San Francisco', 'Miami', 'Seattle').

    Returns:
        A structured environmental care advisory string including temperature, humidity, and plant recommendations.
    """
    try:
        # Geocoding lookup
        encoded_location = urllib.parse.quote(location)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_location}&count=1"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "SproutAgent/1.0"})
        with urllib.request.urlopen(req) as resp:
            geo_data = json.loads(resp.read().decode("utf-8"))

        if not geo_data.get("results"):
            return f"Could not find geographic coordinates for location '{location}'."

        result = geo_data["results"][0]
        lat = result["latitude"]
        lon = result["longitude"]
        city_name = result.get("name", location)

        # Weather lookup
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m&temperature_unit=fahrenheit"
        req_w = urllib.request.Request(weather_url, headers={"User-Agent": "SproutAgent/1.0"})
        with urllib.request.urlopen(req_w) as resp_w:
            w_data = json.loads(resp_w.read().decode("utf-8"))

        current = w_data.get("current", {})
        temp_f = current.get("temperature_2m", 70.0)
        humidity = current.get("relative_humidity_2m", 50.0)

        # Build care advice
        advice = [f"🌤️ Live Weather Care Advisory for {city_name}:"]
        advice.append(f"  • Temperature: {temp_f}°F | Relative Humidity: {humidity}%")

        if humidity < 40:
            advice.append("  • ⚠️ Low Humidity Warning: High risk of dry leaf tips for tropical plants (Ferns, Peace Lily, Calatheas). Recommend daily leaf misting or using a humidity tray.")
        elif humidity > 75:
            advice.append("  • 💧 High Humidity Notice: Ideal for moisture-loving plants. Ensure good air circulation to prevent fungal growth.")
        else:
            advice.append("  • ✅ Balanced Humidity: Moderate humidity level is suitable for most houseplants.")

        if temp_f > 85:
            advice.append("  • ☀️ High Temperature Warning: Soil evaporates moisture faster. Check watering needs more frequently!")
        elif temp_f < 50:
            advice.append("  • ❄️ Cold Temperature Notice: Move tender tropical plants away from cold windows draft.")

        return "\n".join(advice)
    except Exception as e:
        return f"Unable to fetch weather data for '{location}': {e}"


def lookup_botanical_info(plant_species: str) -> str:
    """Fetches official scientific taxonomy and classification data for a plant species from public biodiversity databases (GBIF / Perenual).

    Args:
        plant_species: Scientific or common plant name (e.g. 'Monstera deliciosa', 'Spathiphyllum', 'Sansevieria').

    Returns:
        A structured summary of taxonomy, scientific name, family, genus, and confidence status.
    """
    api_key = os.environ.get("PERENUAL_API_KEY") or os.environ.get("PLANT_API_KEY")

    if api_key:
        try:
            encoded_query = urllib.parse.quote(plant_species)
            perenual_url = f"https://perenual.com/api/species-list?key={api_key}&q={encoded_query}"
            req = urllib.request.Request(perenual_url, headers={"User-Agent": "SproutAgent/1.0"})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("data"):
                item = data["data"][0]
                common = item.get("common_name", plant_species)
                sci = ", ".join(item.get("scientific_name", [plant_species]))
                cycle = item.get("cycle", "N/A")
                watering = item.get("watering", "N/A")
                sunlight = ", ".join(item.get("sunlight", ["N/A"]))
                return (
                    f"🌿 Perenual Botanical Data for '{common}':\n"
                    f"  • Scientific Name: {sci}\n"
                    f"  • Life Cycle: {cycle}\n"
                    f"  • Recommended Watering: {watering}\n"
                    f"  • Sunlight Needs: {sunlight}"
                )
        except Exception:
            pass  # Fallback to GBIF

    # GBIF Public API (No API key required)
    try:
        encoded_query = urllib.parse.quote(plant_species)
        gbif_url = f"https://api.gbif.org/v1/species/match?name={encoded_query}"
        req = urllib.request.Request(gbif_url, headers={"User-Agent": "SproutAgent/1.0"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        match_type = data.get("matchType", "NONE")
        if match_type == "NONE":
            return f"No botanical taxonomy matches found for plant species '{plant_species}'."

        sci_name = data.get("scientificName", plant_species)
        family = data.get("family", "Unknown")
        genus = data.get("genus", "Unknown")
        order = data.get("order", "Unknown")
        rank = data.get("rank", "SPECIES")
        confidence = data.get("confidence", 0)

        return (
            f"🌿 GBIF Botanical Taxonomy for '{plant_species}':\n"
            f"  • Scientific Name: {sci_name}\n"
            f"  • Family: {family}\n"
            f"  • Genus: {genus}\n"
            f"  • Order: {order}\n"
            f"  • Taxonomic Rank: {rank}\n"
            f"  • Classification Confidence: {confidence}%"
        )
    except Exception as e:
        return f"Error looking up botanical info for '{plant_species}': {e}"


def geocode_address(address: str) -> str:
    """Uses Google Maps Geocoding API to convert a physical street address or city into geographical coordinates (latitude and longitude).

    Args:
        address: Address or city string (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA' or 'San Francisco, CA').

    Returns:
        Formatted string containing formatted address, latitude, and longitude.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not configured."

    try:
        encoded_address = urllib.parse.quote(address)
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "SproutAgent/1.0"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        status = data.get("status")
        if status != "OK" or not data.get("results"):
            return f"Geocoding API returned status '{status}' for address '{address}'."

        first = data["results"][0]
        formatted_address = first.get("formatted_address", address)
        loc = first.get("geometry", {}).get("location", {})
        lat = loc.get("lat")
        lng = loc.get("lng")

        return f"📍 Geocoded Result:\n  • Address: {formatted_address}\n  • Location: ({lat}, {lng})"
    except Exception as e:
        return f"Error geocoding address '{address}': {e}"


def find_nearby_places(latitude: float, longitude: float, place_type: str = "florist", radius_meters: float = 5000.0) -> str:
    """Uses Google Maps Places API (New) searchNearby REST endpoint to find nearby places of a given type (e.g. florist, garden center).

    Args:
        latitude: Latitude coordinate of the search center.
        longitude: Longitude coordinate of the search center.
        place_type: Type of place to search for (e.g. 'florist', 'garden_center', 'park').
        radius_meters: Search radius in meters (default: 5000.0 meters).

    Returns:
        A list of matching nearby places with name, formatted address, and location coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not configured."

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.primaryType",
            "User-Agent": "SproutAgent/1.0",
        }
        body = {
            "includedTypes": [place_type],
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "radius": radius_meters,
                }
            },
        }

        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        places = data.get("places", [])
        if not places:
            return f"No nearby places found of type '{place_type}' within {radius_meters} meters."

        summary = [f"🌸 Found {len(places)} nearby places (Type: '{place_type}'):"]
        for idx, p in enumerate(places[:5], start=1):
            name = p.get("displayName", {}).get("text", "Unknown Name")
            address = p.get("formattedAddress", "Unknown Address")
            loc = p.get("location", {})
            lat = loc.get("latitude")
            lng = loc.get("longitude")
            summary.append(f"{idx}. {name}\n   Address: {address}\n   Coordinates: ({lat}, {lng})")

        return "\n".join(summary)
    except Exception as e:
        return f"Error searching nearby places: {e}"


async def generate_plant_image(prompt: str, tool_context: ToolContext) -> str:
    """Generates a realistic image for a plant or botanical item in Sprout's domain using gemini-3.1-flash-lite-image in the global region. Saves the image as an artifact and uploads its bytes directly to Cloud Storage.

    Args:
        prompt: Detailed description of the plant or care setup image to generate (e.g. 'A vibrant Snake Plant in a ceramic pot').
        tool_context: ADK ToolContext provided automatically by the agent framework.

    Returns:
        The public HTTPS Cloud Storage URL (https://storage.googleapis.com/<bucket>/<object>) of the generated image.
    """
    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        if not response.candidates or not response.candidates[0].content.parts:
            return "Failed to generate image: No candidates returned from model."

        part = response.candidates[0].content.parts[0]
        if not hasattr(part, "inline_data") or not part.inline_data:
            return "Failed to generate image: Part did not contain inline image data."

        image_bytes = part.inline_data.data
        mime_type = part.inline_data.mime_type or "image/jpeg"

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"generated_plant_{timestamp}.jpg"

        # (1) Save artifact with tool_context.save_artifact for Playground Artifacts panel
        if tool_context is not None:
            try:
                artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                await tool_context.save_artifact(filename=filename, artifact=artifact_part)
            except Exception as e:
                print(f"Notice: tool_context.save_artifact skipped/error: {e}")

        # (2) Upload image bytes directly to GCS bucket (no local file)
        object_name = f"generated_plants/{filename}"
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(object_name)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{object_name}"
        return public_url
    except Exception as e:
        return f"Error generating image: {e}"


# Configure Agent Platform Code Executor using AgentEngineSandboxCodeExecutor
agent_engine_resource_name = _get_agent_engine_resource_name()
code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)

# Configure Memory Service instance for module reference
memory_service = _get_memory_service()

# Build system prompt with A2uiSchemaManager (version 0.8) and BasicCatalog
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Sprout, an intelligent and friendly Plant Care Assistant. "
        "You help users track their plants, maintain watering schedules, update plant details, "
        "upload plant photos, generate realistic plant images, check weather/humidity care advisories, "
        "look up botanical taxonomy data, geocode addresses, find nearby plant nurseries and florists, "
        "run Python computations in a secure code sandbox, and diagnose plant health issues."
    ),
    workflow_description=(
        "Analyze the request, call necessary tools (`list_plants`, `add_plant`, `update_plant`, `water_plant`, "
        "`check_reminders`, `upload_plant_photo`, `generate_plant_image`, `fetch_weather_care_advisory`, "
        "`lookup_botanical_info`, `geocode_address`, `find_nearby_places`, `load_memory`), and return structured UI when appropriate."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[
        list_plants,
        add_plant,
        update_plant,
        water_plant,
        check_reminders,
        upload_plant_photo,
        generate_plant_image,
        fetch_weather_care_advisory,
        lookup_botanical_info,
        geocode_address,
        find_nearby_places,
        load_memory_tool,
        preload_memory_tool,
    ],
    code_executor=code_executor,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
