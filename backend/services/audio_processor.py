"""
HEALING_WITH_HOPE — services/audio_processor.py
"""

import io
import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    import librosa
    LIBROSA_OK = True
except ImportError:
    LIBROSA_OK = False
    logger.warning("⚠️ librosa not installed")

FEATURE_DIM = 64

class AudioProcessor:
    def extract_features_from_bytes(self, raw: bytes) -> np.ndarray:
        """New method for FastAPI compatibility"""
        try:
            return self._librosa(raw) if LIBROSA_OK else self._dummy(raw)
        except Exception as exc:
            logger.error(f"❌ Feature extraction: {exc}", exc_info=True)
            return None

    def _librosa(self, raw: bytes) -> np.ndarray:
        # Load audio from memory
        y, sr = librosa.load(io.BytesIO(raw), sr=22050, mono=True)
        
        feats = []
        # MFCC (26 features)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        feats += list(np.mean(mfcc, axis=1)) + list(np.std(mfcc, axis=1))
        
        # Chroma (12 features)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        feats += list(np.mean(chroma, axis=1))
        
        # Spectral features
        feats.append(float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))))
        feats.append(float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))))
        feats.append(float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))))
        feats.append(float(np.mean(librosa.feature.zero_crossing_rate(y))))
        feats.append(float(np.mean(librosa.feature.rms(y=y))))
        
        # Pitch tracking
        p, _ = librosa.piptrack(y=y, sr=sr)
        feats.append(float(np.mean(p[p > 0])) if np.any(p > 0) else 0.0)
        
        # Pad/Truncate to 64
        feats = (feats + [0.0] * FEATURE_DIM)[:FEATURE_DIM]
        arr = np.array(feats, dtype=np.float32)
        
        # Normalize
        std = arr.std()
        return (arr - arr.mean()) / std if std > 0 else arr

    def _dummy(self, raw: bytes) -> np.ndarray:
        b = np.frombuffer(raw[:FEATURE_DIM * 4], dtype=np.uint8)
        out = np.zeros(FEATURE_DIM, dtype=np.float32)
        n = min(len(b), FEATURE_DIM)
        out[:n] = b[:n] / 255.0
        return out