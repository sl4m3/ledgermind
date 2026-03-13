from .config import EnrichmentConfig

class PromptBuilder:
    """Handles construction of LLM prompts."""

    @staticmethod
    def build_system_prompt(target: str, rationale: str, config: EnrichmentConfig) -> str:
        lang = config.enrichment_language
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
        lang = config.enrichment_language
        lang_instr = f"Respond strictly in {lang}." if lang != "auto" else ""

        return (
            "You are a Duplicate Detection Expert.\n"
            "### TASK: Analyze the provided documents and group their FIDs into clusters of actual semantic duplicates.\n"
            "### RULES:\n"
            "1. Documents that describe the SAME functional change or hypothesis MUST be grouped together.\n"
            "2. Every provided FID MUST be included in the output exactly once.\n"
            "3. If a document is truly unique, place it in a cluster by itself (list of 1 FID).\n"
            "4. DO NOT write any titles or summaries. Just return the arrays of FIDs.\n"
            f"### OUTPUT RULES: {lang_instr} Return ONLY a JSON object with fields:\n"
            "{\n"
            "  \"clusters\": [\n"
            "    [\"fid_1\", \"fid_2\"], // Group of duplicates\n"
            "    [\"fid_3\"] // Unique item\n"
            "  ],\n"
            "  \"reasoning\": \"Brief explanation of your grouping\"\n"
            "}"
        )

    @staticmethod
    def build_consolidation_prompt(config: EnrichmentConfig) -> str:
        lang = config.enrichment_language
        lang_instr = f"Respond strictly in {lang}." if lang != "auto" else ""

        return (
            "You are a Senior Principal Software Architect writing the FINAL, authoritative technical specification.\n"
            "### TASK: Consolidate the provided knowledge into a single, ultimate truth.\n"
            "### CRITICAL RULES:\n"
            "1. DO NOT mention the source documents, FIDs, or the fact that this is a consolidation.\n"
            "2. DO NOT use phrases like 'These documents describe...', 'The hypothesis states...', or 'Synthesis of...'.\n"
            "3. WRITE AS THE ORIGINAL AUTHOR. Provide the actual technical details, architecture decisions, and facts directly.\n"
            "4. Merge all unique technical details, context, and evidence.\n"
            f"### OUTPUT RULES: {lang_instr} Return ONLY a JSON object with the following fields:\n"
            "{\n"
            "  \"title\": \"Clear, specific technical title (e.g., 'Background Worker Isolation Mechanism')\",\n"
            "  \"target\": \"Best hierarchical path (e.g., core/api/memory)\",\n"
            "  \"rationale\": \"Deep, authoritative Markdown explanation of what is being done and why. Use proper markdown headers and lists.\",\n"
            "  \"compressive_rationale\": \"Exactly 3 sentences summarizing the technical essence\",\n"
            "  \"strengths\": [\"advantage 1\", \"advantage 2\"],\n"
            "  \"objections\": [\"risk 1\", \"risk 2\"],\n"
            "  \"consequences\": [\"impact 1\", \"impact 2\"],\n"
            "  \"keywords\": [\"keyword1\", \"keyword2\", \"keyword3\"],\n"
            "  \"procedural\": [{\"action\": \"...\", \"expected_outcome\": \"...\", \"rationale\": \"...\"}]\n"
            "}"
        )

    @staticmethod
    def build_target_conflict_resolution_prompt(config: EnrichmentConfig, proposed_target: str, consolidated_docs: list, conflict_docs: list) -> str:
        """
        V7.8: Build prompt for resolving target conflicts during consolidation.
        
        Args:
            config: Enrichment configuration
            proposed_target: Target proposed by LLM for consolidation
            consolidated_docs: List of documents being consolidated
            conflict_docs: List of existing active decisions with same target
            
        Returns:
            Formatted prompt string
        """
        lang = config.enrichment_language
        lang_instr = f"Respond strictly in {lang}." if lang != "auto" else ""
        
        return (
            "You are a Knowledge Architecture Expert.\n"
            "### TASK: Resolve a target conflict during knowledge consolidation.\n"
            "### CONTEXT: A consolidation operation proposed a target that is already in use by existing active decisions.\n"
            f"### PROPOSED TARGET: {proposed_target}\n"
            "### YOUR TASK: Determine if the conflicting decisions represent the SAME knowledge as the consolidated documents, or DIFFERENT knowledge.\n"
            "### DECISION CRITERIA:\n"
            "1. If SAME KNOWLEDGE: Return action='merge' to include all conflicts in the consolidation.\n"
            "2. If DIFFERENT KNOWLEDGE: Return action='separate' and propose a NEW unique target that clearly distinguishes the consolidated knowledge from the conflicts.\n"
            f"### OUTPUT RULES: {lang_instr} Return ONLY a JSON object with the following fields:\n"
            "{\n"
            "  \"action\": \"merge\" | \"separate\",\n"
            "  \"reason\": \"Brief explanation of your decision based on semantic analysis\",\n"
            "  \"new_target\": \"proposed.new.target\"  // Required only if action='separate'. Must be specific and unique.\n"
            "}"
        )

    @staticmethod
    def wrap_with_data(instructions: str, data: str, config: EnrichmentConfig) -> str:
        lang_enf = ""
        if config.enrichment_language != "auto":
            lang_enf = f"\n\nCRITICAL: YOUR ENTIRE RESPONSE MUST BE IN {config.enrichment_language.upper()}."

        return (
            "### RAW DATA FOR ANALYSIS\n<data_block>\n"
            f"{data or ''}\n"
            "</data_block>\n\n"
            "### TASK INSTRUCTIONS\n"
            f"{instructions}{lang_enf}\n\n"
            "Respond ONLY with the JSON object."
        )
