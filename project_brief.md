# Project Brief: Sprout (Plant Care Assistant)

## Executive Summary
Sprout is an AI-powered agentic application designed to help plant owners care for their indoor and outdoor plants. It maintains a plant inventory, calculates watering schedules, sends reminders, and provides AI-powered multimodal health diagnosis from plant photos using Gemini 2.5 Flash.

---

## Key Features & Capabilities

### 1. Plant Inventory & Tracking
- Register plants with details: name, species, location (e.g. Living Room, Balcony), and watering frequency (in days).
- View all tracked plants and their last watered timestamps.

### 2. Smart Water Reminders
- Calculate days elapsed since last watering.
- Flag plants that are currently due or overdue for watering.
- Easily mark plants as watered to reset their schedules.

### 3. Multimodal Photo Diagnosis
- Analyze photos of plant leaves, stems, or soil using Gemini 2.5 Flash vision.
- Identify common issues such as overwatering, under-watering, pests, or nutrient deficiencies.
- Provide actionable, step-by-step recovery recommendations.

### 4. Pet Safety & Guardrails
- Automatically detect species toxic to household pets (cats and dogs).
- Display clear warnings when registering or discussing pet-toxic plants (e.g., Peace Lily, Monstera, Pothos).
- Recommend safe, non-toxic remedies over harsh chemicals.

---

## Technical Architecture

- **Framework**: Agent Development Kit (ADK) in Python
- **Model**: Gemini 2.5 Flash (`gemini-2.5-flash`)
- **Tools Included**:
  - `add_plant(name, species, location, watering_interval_days)`
  - `list_plants()`
  - `water_plant(name)`
  - `check_reminders()`
- **Storage**: Local JSON/in-memory plant registry
- **Execution Mode**: Local interactive testing via `agents-cli run` and `agents-cli playground`

---

## Success Criteria & Evaluation

- **Tool Accuracy**: 100% correct tool execution for inventory and watering updates.
- **Safety**: 100% inclusion of pet toxicity warnings for known toxic species.
- **Evaluation Benchmark**: Achieve mean quality score >= 4.0/5.0 on `agents-cli eval run`.
