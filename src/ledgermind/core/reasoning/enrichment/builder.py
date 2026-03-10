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
            "### TASK: Analyze the provided list of documents and group them into clusters of actual semantic duplicates.\n"
            "### CONSOLIDATION RULES:\n"
            "1. Every single FID from the provided list MUST be included in the output JSON exactly once.\n"
            "2. If documents are duplicates, group their FIDs together and provide synthesized 'unified_title', 'unified_target', and 'unified_rationale'.\n"
            "3. If a document is unique, place it in a cluster by itself (list of 1 FID) and explain why it is unique.\n"
            f"### OUTPUT RULES: {lang_instr} Return ONLY a JSON object with fields:\n"
            "{\n"
            "  \"clusters\": [\n"
            "    {\n"
            "      \"fids\": [\"id_1\", \"id_2\"],\n"
            "      \"unified_title\": \"Combined Title\",\n"
            "      \"unified_target\": \"core/reasoning/merging\",\n"
            "      \"unified_rationale\": \"Synthesized Markdown content...\",\n"
            "      \"keywords\": [\"key1\", \"key2\"]\n"
            "    },\n"
            "    {\n"
            "      \"fids\": [\"id_3\"], // Unique document\n"
            "      \"reasoning\": \"Explain why unique\"\n"
            "    }\n"
            "  ],\n"
            "  \"global_reasoning\": \"Overview of the clustering process\"\n"
            "}"
        )

    @staticmethod
    def build_consolidation_prompt(config: EnrichmentConfig) -> str:
        lang = config.preferred_language
        lang_instr = f"Respond strictly in {lang}." if lang != "auto" else ""
        
        return (
            "You are a Senior Knowledge Architect.\n"
            "### TASK: Consolidate the following CONFIRMED duplicates into a single, high-quality knowledge record.\n"
            "### RULES:\n"
            "1. These documents describe the same event/decision. Merge them into one.\n"
            "2. Provide a 'unified_title' that is technically precise.\n"
            "3. Provide a 'unified_target' representing the best hierarchical path.\n"
            "4. Provide a 'unified_rationale' in Markdown, preserving all critical details and evidence.\n"
            f"### OUTPUT RULES: {lang_instr} Return ONLY a JSON object with fields:\n"
            "{\n"
            "  \"clusters\": [{\n"
            "    \"fids\": [\"all_provided_fids_here\"],\n"
            "    \"unified_title\": \"Unified Title\",\n"
            "    \"unified_target\": \"path/to/target\",\n"
            "    \"unified_rationale\": \"Full Markdown synthesis...\",\n"
            "    \"keywords\": [\"key1\", \"key2\", ...]\n"
            "  }],\n"
            "  \"global_reasoning\": \"Summary of consolidation\"\n"
            "}"
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
