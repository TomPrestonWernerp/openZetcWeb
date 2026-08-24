"""知识库运行时单例。"""

import os

from openzetc.config import config
from openzetc.knowledge.factory import KnowledgeBaseFactory
from openzetc.knowledge.implementations.dify import DifyKB
from openzetc.knowledge.implementations.milvus import MilvusKB
from openzetc.knowledge.implementations.notion import NotionKB
from openzetc.knowledge.manager import KnowledgeBaseManager

if os.environ.get("LITE_MODE", "").lower() not in ("true", "1"):
    KnowledgeBaseFactory.register(MilvusKB)
KnowledgeBaseFactory.register(DifyKB)
KnowledgeBaseFactory.register(NotionKB)

knowledge_base = KnowledgeBaseManager(os.path.join(config.save_dir, "knowledge_base_data"))
