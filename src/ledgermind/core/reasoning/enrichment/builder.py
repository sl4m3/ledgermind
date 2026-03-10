from .config import EnrichmentConfig

class PromptBuilder:
    """Handles construction of LLM prompts."""
    
    @staticmethod
    def build_system_prompt(target: str, rationale: str, config: EnrichmentConfig) -> str:
        lang = config.preferred_language
        lang_instr = f"Respond strictly in {lang}." if lang != "auto" else "Respond in the original language."
        
        return (
            "You are a Senior Principal Software Architect.\n"
            f"### TASK: Analyze activity for '{target}' and create a unified knowledge entry.\n"
            f"### CONTEXT: {rationale}\n"
            f"### RULES: {lang_instr} Return ONLY JSON with fields:\n"
            "1. title: Professional technical title.\n"
            "2. rationale: Full, detailed architectural rationale focusing on 'what' and 'why'. Use Markdown.\n"
            "3. compressive: Exactly 3 sentences summarizing the technical essence.\n"
            "4. strengths: List of technical advantages.\n"
            "5. objections: List of potential risks or drawbacks.\n"
            "6. consequences: List of architectural impacts.\n"
            "7. estimated_utility: Number (0.0-1.0) representing current usefulness.\n"
            "8. estimated_removal_cost: Number (0.0-1.0) representing the risk of losing this knowledge.\n"
            f"9. keywords: A flat list of 4-6 items. For every semantic concept, you MUST include two separate strings: one in {lang} and one in English (e.g., ['Слоистая архитектура', 'Layered Architecture', 'Инъекция зависимостей', 'Dependency Injection']).\n"
            "10. procedural: List of {action, expected_outcome, rationale} steps representing the workflow."
        )

    @staticmethod
    def build_clustering_prompt(config: EnrichmentConfig) -> str:
        lang = config.preferred_language
        lang_instr = f"Respond strictly in {lang}." if lang != "auto" else ""
        
        return (
            "You are a Knowledge Architect and Duplicate Detection Expert.\n"
            "### TASK: Analyze the provided list of knowledge documents and group them into clusters of actual semantic duplicates.\n"
            "### DEFINITION: A cluster should contain documents that describe the exact same event, decision, or hypothesis.\n"
            f"### RULES: {lang_instr} Return ONLY a JSON object with fields:\n"
            "1. clusters: A list of lists, where each sub-list contains document FIDs that are duplicates. If a document is unique, it MUST be in a sub-list by itself.\n"
            "2. reasoning: A brief explanation of your clustering logic.\n"
            "### EXAMPLE: {\"clusters\": [[\"fid_1\", \"fid_2\"], [\"fid_3\"]], \"reasoning\": \"1 and 2 are same, 3 is unique\"}"
        )

    @staticmethod
    def wrap_with_data(instructions: str, data: str, config: EnrichmentConfig) -> str:
        lang_enf = ""
        if config.preferred_language != "auto":
            lang_enf = f"\n\nCRITICAL: YOUR ENTIRE RESPONSE MUST BE IN {config.preferred_language.upper()}."
            
        return (
            "### RAW DATA FOR ANALYSIS\n<data_block>\n"
            f"{data or ''}\n"
            "</data_block>\n\n"
            "### TASK INSTRUCTIONS\n"
            f"{instructions}{lang_enf}\n\n"
            "Respond ONLY with the JSON object."
        )
