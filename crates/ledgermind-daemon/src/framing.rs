use std::io::{self, Read, Write};

use thiserror::Error;

pub const MAX_FRAME_BYTES: usize = 8 * 1024 * 1024;

#[derive(Debug, Error)]
pub enum FrameError {
    #[error("frame stream ended")]
    Eof,

    #[error("frame header was truncated")]
    TruncatedHeader,

    #[error("frame payload was truncated")]
    TruncatedPayload,

    #[error("frame exceeds maximum size: {0} bytes")]
    TooLarge(usize),

    #[error("frame I/O failed: {0}")]
    Io(#[from] io::Error),
}

pub fn read_frame<R: Read>(reader: &mut R) -> Result<Option<Vec<u8>>, FrameError> {
    let mut header = [0_u8; 4];
    let mut read = 0;
    while read < header.len() {
        let count = reader.read(&mut header[read..])?;
        if count == 0 {
            if read == 0 {
                return Ok(None);
            }
            return Err(FrameError::TruncatedHeader);
        }
        read += count;
    }
    let length = u32::from_be_bytes(header) as usize;
    if length > MAX_FRAME_BYTES {
        return Err(FrameError::TooLarge(length));
    }
    let mut payload = vec![0_u8; length];
    reader.read_exact(&mut payload).map_err(|error| {
        if error.kind() == io::ErrorKind::UnexpectedEof {
            FrameError::TruncatedPayload
        } else {
            FrameError::Io(error)
        }
    })?;
    Ok(Some(payload))
}

pub fn write_frame<W: Write>(writer: &mut W, payload: &[u8]) -> Result<(), FrameError> {
    if payload.len() > MAX_FRAME_BYTES {
        return Err(FrameError::TooLarge(payload.len()));
    }
    let length = u32::try_from(payload.len()).expect("MAX_FRAME_BYTES fits in u32");
    writer.write_all(&length.to_be_bytes())?;
    writer.write_all(payload)?;
    writer.flush()?;
    Ok(())
}
