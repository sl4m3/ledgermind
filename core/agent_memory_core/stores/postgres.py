import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Index, and_, select, delete, JSON, Integer
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from agent_memory_core.stores.interfaces import MetadataStore, VectorProvider, EpisodicProvider
from agent_memory_core.core.schemas import MemoryEvent

logger = logging.getLogger("agent-memory-core.postgres")
Base = declarative_base()

class EventEntity(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String)
    kind = Column(String)
    content = Column(Text)
    context = Column(JSON)
    timestamp = Column(DateTime)
    status = Column(String, default='active')
    linked_id = Column(String)

class DecisionEntity(Base):
    __tablename__ = 'decisions'

    fid = Column(String, primary_key=True)
    namespace = Column(String, default="default", nullable=False)
    target = Column(String, nullable=False)
    status = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    superseded_by = Column(String)
    text_preview = Column(Text)
    metadata_json = Column(JSON)
    hit_count = Column(Integer, default=0)
    
    try:
        from pgvector.sqlalchemy import Vector
        embedding = Column(Vector(1536))
    except (ImportError, Exception):
        from sqlalchemy import PickleType
        embedding = Column(PickleType)

    __table_args__ = (
        Index('idx_decision_status', 'status'),
        Index('idx_decision_target', 'target'),
    )

class PostgresStore(MetadataStore, VectorProvider, EpisodicProvider):
    def __init__(self, connection_string: str, embedding_dim: int = 1536):
        from sqlalchemy import create_engine
        self.engine = create_engine(connection_string)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.embedding_dim = embedding_dim

    # MetadataStore implementation
    def upsert(self, fid: str, target: str, status: str, kind: str, timestamp: datetime, superseded_by: Optional[str] = None, namespace: str = "default"):
        with self.Session() as session:
            decision = session.query(DecisionEntity).filter_by(fid=fid).first()
            if not decision:
                decision = DecisionEntity(fid=fid)
            
            decision.namespace = namespace
            decision.target = target
            decision.status = status
            decision.kind = kind
            decision.timestamp = timestamp
            decision.superseded_by = superseded_by
            
            session.add(decision)
            session.commit()

    def get_active_fid(self, target: str, namespace: str = "default") -> Optional[str]:
        with self.Session() as session:
            res = session.execute(
                select(DecisionEntity.fid).where(
                    and_(
                        DecisionEntity.namespace == namespace,
                        DecisionEntity.target == target,
                        DecisionEntity.status == 'active',
                        DecisionEntity.kind == 'decision'
                    )
                )
            ).fetchone()
            return res[0] if res else None

    def list_all(self) -> List[Dict[str, Any]]:
        with self.Session() as session:
            results = session.query(DecisionEntity).all()
            return [
                {
                    "fid": d.fid,
                    "target": d.target,
                    "status": d.status,
                    "kind": d.kind,
                    "timestamp": d.timestamp,
                    "superseded_by": d.superseded_by
                } for d in results
            ]

    def delete(self, fid: str):
        with self.Session() as session:
            session.execute(delete(DecisionEntity).where(DecisionEntity.fid == fid))
            session.commit()

    def clear(self):
        with self.Session() as session:
            session.execute(delete(DecisionEntity))
            session.execute(delete(EventEntity))
            session.commit()

    def increment_hit(self, fid: str):
        with self.Session() as session:
            session.query(DecisionEntity).filter_by(fid=fid).update(
                {DecisionEntity.hit_count: DecisionEntity.hit_count + 1}
            )
            session.commit()

    # VectorProvider implementation
    def update_index(self, decision_id: str, embedding: List[float], text_preview: str, metadata: dict = None):
        with self.Session() as session:
            decision = session.query(DecisionEntity).filter_by(fid=decision_id).first()
            if not decision:
                decision = DecisionEntity(fid=decision_id, target="unknown", status="unknown", kind="unknown", timestamp=datetime.now())
            
            decision.embedding = embedding
            decision.text_preview = text_preview
            decision.metadata_json = metadata
            
            session.add(decision)
            session.commit()

    def delete_from_index(self, decision_id: str):
        self.delete(decision_id)

    def search(self, query_embedding: List[float], limit: int = 5, 
               start_time: Optional[datetime] = None, 
               end_time: Optional[datetime] = None,
               namespace: str = "default") -> List[Tuple[str, float, str]]:
        with self.Session() as session:
            query = select(
                DecisionEntity.fid,
                DecisionEntity.embedding.cosine_distance(query_embedding).label('distance'),
                DecisionEntity.text_preview
            ).where(DecisionEntity.namespace == namespace)
            
            if start_time:
                query = query.where(DecisionEntity.timestamp >= start_time)
            if end_time:
                query = query.where(DecisionEntity.timestamp <= end_time)
                
            query = query.order_by('distance').limit(limit)
            
            results = session.execute(query).fetchall()
            return [(r.fid, 1.0 - float(r.distance), r.text_preview) for r in results]

    # EpisodicProvider implementation
    def append(self, event: MemoryEvent, linked_id: Optional[str] = None) -> int:
        with self.Session() as session:
            context_data = event.context
            if hasattr(context_data, 'model_dump'):
                context_dict = context_data.model_dump(mode='json')
            else:
                context_dict = context_data

            new_event = EventEntity(
                source=event.source,
                kind=event.kind,
                content=event.content,
                context=context_dict,
                timestamp=event.timestamp,
                linked_id=linked_id
            )
            session.add(new_event)
            session.commit()
            return new_event.id

    def link_to_semantic(self, event_id: int, semantic_id: str):
        with self.Session() as session:
            session.query(EventEntity).filter_by(id=event_id).update({"linked_id": semantic_id})
            session.commit()

    def query(self, limit: int = 100, status: Optional[str] = 'active') -> List[Dict[str, Any]]:
        with self.Session() as session:
            stmt = select(EventEntity)
            if status:
                stmt = stmt.where(EventEntity.status == status)
            stmt = stmt.order_by(EventEntity.id.desc()).limit(limit)
            
            results = session.execute(stmt).scalars().all()
            return [
                {
                    "id": e.id,
                    "source": e.source,
                    "kind": e.kind,
                    "content": e.content,
                    "context": e.context,
                    "timestamp": e.timestamp.isoformat(),
                    "status": e.status,
                    "linked_id": e.linked_id
                } for e in results
            ]

    def mark_archived(self, event_ids: List[int]):
        if not event_ids: return
        with self.Session() as session:
            session.query(EventEntity).filter(EventEntity.id.in_(event_ids)).update({"status": "archived"}, synchronize_session=False)
            session.commit()

    def physical_prune(self, event_ids: List[int]):
        if not event_ids: return
        with self.Session() as session:
            session.query(EventEntity).filter(
                and_(EventEntity.id.in_(event_ids), EventEntity.linked_id == None)
            ).delete(synchronize_session=False)
            session.commit()
