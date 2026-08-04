use std::{fmt, str::FromStr};

use serde::{Deserialize, Deserializer, Serialize, de::Error as DeError};

use crate::DomainError;

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd, Hash, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Phase {
    Pattern,
    Emergent,
    Canonical,
}

impl Phase {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Pattern => "pattern",
            Self::Emergent => "emergent",
            Self::Canonical => "canonical",
        }
    }
}

impl TryFrom<&str> for Phase {
    type Error = DomainError;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        match value {
            "pattern" => Ok(Self::Pattern),
            "emergent" => Ok(Self::Emergent),
            "canonical" => Ok(Self::Canonical),
            value => Err(DomainError::UnknownPhase {
                value: value.to_owned(),
            }),
        }
    }
}

impl TryFrom<String> for Phase {
    type Error = DomainError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        Self::try_from(value.as_str())
    }
}

impl FromStr for Phase {
    type Err = DomainError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        Self::try_from(value)
    }
}

impl fmt::Display for Phase {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

impl<'de> Deserialize<'de> for Phase {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        Self::try_from(value).map_err(D::Error::custom)
    }
}
