use serde::{Deserialize, Deserializer, Serialize, Serializer};
use serde_json::{Map, Value};
use time::OffsetDateTime;

use crate::{DomainError, DomainResult, HypothesisId, KnowledgeId, RevisionId};

fn required(value: String, field: &'static str) -> DomainResult<String> {
    if value.trim().is_empty() {
        return Err(DomainError::EmptyField { field });
    }
    Ok(value)
}

fn canonicalize(value: Value) -> Value {
    match value {
        Value::Array(values) => Value::Array(values.into_iter().map(canonicalize).collect()),
        Value::Object(values) => {
            let mut ordered = Map::new();
            for (key, value) in values {
                ordered.insert(key, canonicalize(value));
            }
            Value::Object(ordered)
        }
        value => value,
    }
}

fn serialize_snapshot<S>(snapshot: &Value, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    let json = serde_json::to_string(snapshot).map_err(serde::ser::Error::custom)?;
    serializer.serialize_str(&json)
}

fn deserialize_snapshot<'de, D>(deserializer: D) -> Result<Value, D::Error>
where
    D: Deserializer<'de>,
{
    let json = String::deserialize(deserializer)?;
    let snapshot: Value = serde_json::from_str(&json).map_err(serde::de::Error::custom)?;
    if !snapshot.is_object() {
        return Err(serde::de::Error::custom(
            "snapshot_json must be a JSON object",
        ));
    }
    Ok(canonicalize(snapshot))
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "KnowledgeRevisionWire")]
pub struct KnowledgeRevision {
    revision_id: RevisionId,
    knowledge_id: KnowledgeId,
    version: u64,
    event_type: String,
    #[serde(rename = "snapshot_json", serialize_with = "serialize_snapshot")]
    snapshot: Value,
    cause_hypothesis_id: Option<HypothesisId>,
    created_at: OffsetDateTime,
}

impl KnowledgeRevision {
    pub fn from_snapshot(
        revision_id: RevisionId,
        knowledge_id: KnowledgeId,
        version: u64,
        event_type: String,
        snapshot: Value,
        cause_hypothesis_id: Option<HypothesisId>,
        created_at: OffsetDateTime,
    ) -> DomainResult<Self> {
        if version < 1 {
            return Err(DomainError::InvalidVersion {
                field: "version",
                minimum: 1,
                actual: version,
            });
        }
        let event_type = required(event_type, "event_type")?;
        if !snapshot.is_object() {
            return Err(DomainError::SnapshotMustBeObject);
        }

        Ok(Self {
            revision_id,
            knowledge_id,
            version,
            event_type,
            snapshot: canonicalize(snapshot),
            cause_hypothesis_id,
            created_at,
        })
    }

    pub fn from_json(
        revision_id: RevisionId,
        knowledge_id: KnowledgeId,
        version: u64,
        event_type: String,
        snapshot_json: String,
        cause_hypothesis_id: Option<HypothesisId>,
        created_at: OffsetDateTime,
    ) -> DomainResult<Self> {
        let snapshot =
            serde_json::from_str(&snapshot_json).map_err(|error| DomainError::InvalidSnapshot {
                reason: error.to_string(),
            })?;
        Self::from_snapshot(
            revision_id,
            knowledge_id,
            version,
            event_type,
            snapshot,
            cause_hypothesis_id,
            created_at,
        )
    }

    pub fn revision_id(&self) -> &RevisionId {
        &self.revision_id
    }

    pub fn knowledge_id(&self) -> &KnowledgeId {
        &self.knowledge_id
    }

    pub const fn version(&self) -> u64 {
        self.version
    }

    pub fn event_type(&self) -> &str {
        &self.event_type
    }

    pub fn snapshot_json(&self) -> String {
        serde_json::to_string(&self.snapshot).expect("Value serialization is infallible")
    }

    pub fn snapshot(&self) -> &Value {
        &self.snapshot
    }

    pub fn cause_hypothesis_id(&self) -> Option<&HypothesisId> {
        self.cause_hypothesis_id.as_ref()
    }

    pub const fn created_at(&self) -> OffsetDateTime {
        self.created_at
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct KnowledgeRevisionWire {
    revision_id: RevisionId,
    knowledge_id: KnowledgeId,
    version: u64,
    event_type: String,
    #[serde(rename = "snapshot_json", deserialize_with = "deserialize_snapshot")]
    snapshot: Value,
    cause_hypothesis_id: Option<HypothesisId>,
    created_at: OffsetDateTime,
}

impl TryFrom<KnowledgeRevisionWire> for KnowledgeRevision {
    type Error = DomainError;

    fn try_from(value: KnowledgeRevisionWire) -> Result<Self, Self::Error> {
        Self::from_snapshot(
            value.revision_id,
            value.knowledge_id,
            value.version,
            value.event_type,
            value.snapshot,
            value.cause_hypothesis_id,
            value.created_at,
        )
    }
}
