/**
 * PlaybackControl Component
 * Timeline slider for activity replay
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { Play, Pause, SkipBack, SkipForward, Clock } from 'lucide-react';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

export default function PlaybackControl({ onFrameChange, onPlaybackData }) {
  const [frames, setFrames] = useState([]);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [hours, setHours] = useState(24);
  
  const intervalRef = useRef(null);
  
  // Fetch playback data
  const fetchPlayback = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/geo/playback?hours=${hours}&step=30`);
      const data = await res.json();
      if (data.ok) {
        setFrames(data.frames || []);
        setCurrentFrame(0);
        if (onPlaybackData) onPlaybackData(data);
      }
    } catch (err) {
      console.error('Playback fetch error:', err);
    } finally {
      setIsLoading(false);
    }
  }, [hours, onPlaybackData]);
  
  // Load on mount
  useEffect(() => {
    fetchPlayback();
  }, [fetchPlayback]);
  
  // Notify parent of frame change
  useEffect(() => {
    if (frames.length > 0 && onFrameChange) {
      onFrameChange(frames[currentFrame]);
    }
  }, [currentFrame, frames, onFrameChange]);
  
  // Playback loop
  useEffect(() => {
    if (isPlaying && frames.length > 0) {
      intervalRef.current = setInterval(() => {
        setCurrentFrame(prev => {
          if (prev >= frames.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 1000 / speed);
    }
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isPlaying, frames.length, speed]);
  
  const togglePlay = () => {
    if (currentFrame >= frames.length - 1) {
      setCurrentFrame(0);
    }
    setIsPlaying(!isPlaying);
  };
  
  const skipToStart = () => {
    setCurrentFrame(0);
    setIsPlaying(false);
  };
  
  const skipToEnd = () => {
    setCurrentFrame(frames.length - 1);
    setIsPlaying(false);
  };
  
  const handleSliderChange = (e) => {
    setCurrentFrame(parseInt(e.target.value));
    setIsPlaying(false);
  };
  
  const currentFrameData = frames[currentFrame] || {};
  
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4" data-testid="playback-control">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
          <Clock className="w-4 h-4 text-teal-500" />
          Відтворення активності
        </h3>
        
        <div className="flex items-center gap-2">
          <select
            value={hours}
            onChange={(e) => setHours(parseInt(e.target.value))}
            className="text-xs bg-gray-100 border-0 rounded px-2 py-1"
          >
            <option value={6}>6 год</option>
            <option value={12}>12 год</option>
            <option value={24}>24 год</option>
            <option value={48}>48 год</option>
          </select>
          
          <select
            value={speed}
            onChange={(e) => setSpeed(parseFloat(e.target.value))}
            className="text-xs bg-gray-100 border-0 rounded px-2 py-1"
          >
            <option value={0.5}>0.5x</option>
            <option value={1}>1x</option>
            <option value={2}>2x</option>
            <option value={5}>5x</option>
          </select>
        </div>
      </div>
      
      {/* Current time display */}
      <div className="text-center mb-3">
        <span className="text-2xl font-bold text-gray-900">
          {currentFrameData.timestampLocal || '--:--'}
        </span>
        <span className="text-sm text-gray-500 ml-2">
          {currentFrameData.newEvents || 0} нових • {currentFrameData.totalEvents || 0} всього
        </span>
      </div>
      
      {/* Controls */}
      <div className="flex items-center justify-center gap-3 mb-3">
        <button
          onClick={skipToStart}
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"
          title="На початок"
        >
          <SkipBack className="w-5 h-5" />
        </button>
        
        <button
          onClick={togglePlay}
          disabled={isLoading || frames.length === 0}
          className={`p-3 rounded-full ${
            isPlaying 
              ? 'bg-amber-500 hover:bg-amber-600' 
              : 'bg-teal-500 hover:bg-teal-600'
          } text-white disabled:opacity-50`}
          data-testid="playback-play-btn"
        >
          {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
        </button>
        
        <button
          onClick={skipToEnd}
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"
          title="В кінець"
        >
          <SkipForward className="w-5 h-5" />
        </button>
      </div>
      
      {/* Timeline slider */}
      <div className="px-2">
        <input
          type="range"
          min={0}
          max={Math.max(0, frames.length - 1)}
          value={currentFrame}
          onChange={handleSliderChange}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-teal-500"
          data-testid="playback-slider"
        />
        
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>{frames[0]?.timestampLocal || '--:--'}</span>
          <span>Кадр {currentFrame + 1} / {frames.length}</span>
          <span>{frames[frames.length - 1]?.timestampLocal || '--:--'}</span>
        </div>
      </div>
    </div>
  );
}
