use std::{fmt, str::FromStr};

use serde::{Deserialize, Deserializer, Serialize, de::Error as DeError};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::errors::IdentifierError;

fn validate_non_empty(value: String, type_name: &'static str) -> Result<String, IdentifierError> {
    if value.trim().is_empty() {
        return Err(IdentifierError::Empty { type_name });
    }
    Ok(value)
}

fn validate_sha256(value: String, type_name: &'static str) -> Result<String, IdentifierError> {
    let valid = value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase());
    if !valid {
        return Err(IdentifierError::InvalidSha256 { type_name });
    }
    Ok(value)
}

macro_rules! typed_identifier {
    ($name:ident) => {
        #[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize)]
        #[serde(transparent)]
        pub struct $name(String);

        impl $name {
            const TYPE_NAME: &'static str = stringify!($name);

            pub fn new(value: impl Into<String>) -> Result<Self, IdentifierError> {
                Ok(Self(validate_non_empty(value.into(), Self::TYPE_NAME)?))
            }

            pub fn from_uuid(value: Uuid) -> Self {
                Self(value.to_string())
            }

            pub fn as_str(&self) -> &str {
                &self.0
            }
        }

        impl TryFrom<String> for $name {
            type Error = IdentifierError;

            fn try_from(value: String) -> Result<Self, Self::Error> {
                Self::new(value)
            }
        }

        impl TryFrom<&str> for $name {
            type Error = IdentifierError;

            fn try_from(value: &str) -> Result<Self, Self::Error> {
                Self::new(value)
            }
        }

        impl From<$name> for String {
            fn from(value: $name) -> Self {
                value.0
            }
        }

        impl AsRef<str> for $name {
            fn as_ref(&self) -> &str {
                self.as_str()
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str(self.as_str())
            }
        }

        impl FromStr for $name {
            type Err = IdentifierError;

            fn from_str(value: &str) -> Result<Self, Self::Err> {
                Self::try_from(value)
            }
        }

        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
            where
                D: Deserializer<'de>,
            {
                let value = String::deserialize(deserializer)?;
                Self::try_from(value).map_err(D::Error::custom)
            }
        }
    };
}

typed_identifier!(MemorySpaceId);
typed_identifier!(HypothesisId);
typed_identifier!(KnowledgeId);
typed_identifier!(RevisionId);
typed_identifier!(ModelTaskId);
typed_identifier!(ProjectionEventId);

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(transparent)]
pub struct IdempotencyKey(String);

impl IdempotencyKey {
    const TYPE_NAME: &'static str = "IdempotencyKey";

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl TryFrom<String> for IdempotencyKey {
    type Error = IdentifierError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        Ok(Self(validate_sha256(value, Self::TYPE_NAME)?))
    }
}

impl TryFrom<&str> for IdempotencyKey {
    type Error = IdentifierError;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        Self::try_from(value.to_owned())
    }
}

impl From<IdempotencyKey> for String {
    fn from(value: IdempotencyKey) -> Self {
        value.0
    }
}

impl AsRef<str> for IdempotencyKey {
    fn as_ref(&self) -> &str {
        self.as_str()
    }
}

impl fmt::Display for IdempotencyKey {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

impl FromStr for IdempotencyKey {
    type Err = IdentifierError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        Self::try_from(value)
    }
}

impl<'de> Deserialize<'de> for IdempotencyKey {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        Self::try_from(value).map_err(D::Error::custom)
    }
}

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(transparent)]
pub struct Sha256Digest(String);

impl Sha256Digest {
    const TYPE_NAME: &'static str = "Sha256Digest";

    pub fn from_bytes(value: &[u8]) -> Self {
        let digest = Sha256::digest(value);
        Self(format!("sha256:{}", hex::encode(digest)))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl TryFrom<String> for Sha256Digest {
    type Error = IdentifierError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        Ok(Self(validate_sha256(value, Self::TYPE_NAME)?))
    }
}

impl TryFrom<&str> for Sha256Digest {
    type Error = IdentifierError;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        Self::try_from(value.to_owned())
    }
}

impl From<Sha256Digest> for String {
    fn from(value: Sha256Digest) -> Self {
        value.0
    }
}

impl AsRef<str> for Sha256Digest {
    fn as_ref(&self) -> &str {
        self.as_str()
    }
}

impl fmt::Display for Sha256Digest {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

impl FromStr for Sha256Digest {
    type Err = IdentifierError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        Self::try_from(value)
    }
}

impl<'de> Deserialize<'de> for Sha256Digest {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        Self::try_from(value).map_err(D::Error::custom)
    }
}
