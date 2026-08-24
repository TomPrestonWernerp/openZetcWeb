"""文档处理器注册表。"""

PROCESSOR_TYPES = {
    "rapid_ocr": ("openzetc.knowledge.parser.rapid_ocr", "RapidOCRParser"),
    "mineru_ocr": ("openzetc.knowledge.parser.mineru", "MinerUParser"),
    "mineru_official": ("openzetc.knowledge.parser.mineru_official", "MinerUOfficialParser"),
    "pp_structure_v3_ocr": ("openzetc.knowledge.parser.pp_structure_v3", "PPStructureV3Parser"),
    "deepseek_ocr": ("openzetc.knowledge.parser.deepseek_ocr", "DeepSeekOCRParser"),
    "paddleocr_vl_1_6": ("openzetc.knowledge.parser.paddleocr_api", "PaddleOCRVLParser"),
    "paddleocr_pp_ocrv6": ("openzetc.knowledge.parser.paddleocr_api", "PaddleOCRPPOCRv6Parser"),
}
