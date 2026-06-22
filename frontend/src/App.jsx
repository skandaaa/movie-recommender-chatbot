import { useState } from "react";
import axios from "axios";
import "./App.css";

const TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w300";
const TMDB_IMAGE_LARGE = "https://image.tmdb.org/t/p/w500";
const TMDB_LOGO_BASE = "https://image.tmdb.org/t/p/w92";

function MovieCard({ movie, onClick }) {
  return (
    <div className="movie-card" onClick={() => onClick(movie.id)}>
      {movie.poster_path ? (
        <img
          src={`${TMDB_IMAGE_BASE}${movie.poster_path}`}
          alt={movie.title}
          className="movie-poster"
        />
      ) : (
        <div className="movie-poster no-poster">No Image</div>
      )}
      <div className="movie-info">
        <h3 className="movie-title">{movie.title}</h3>
        <div className="movie-meta">
          <span className="movie-year">
            {movie.release_date ? movie.release_date.slice(0, 4) : "N/A"}
          </span>
          <span className="movie-rating">
            ⭐ {movie.vote_average ? movie.vote_average.toFixed(1) : "N/A"}
          </span>
        </div>
        <p className="movie-overview">{movie.overview}</p>
      </div>
    </div>
  );
}

function FilterBadges({ filters }) {
  const badges = [];
  if (filters.genre) badges.push(`Genre: ${filters.genre}`);
  if (filters.language) badges.push(`Language: ${filters.language}`);
  if (filters.max_runtime_minutes) badges.push(`Under ${filters.max_runtime_minutes} min`);
  if (filters.min_runtime_minutes) badges.push(`Over ${filters.min_runtime_minutes} min`);
  if (filters.min_rating) badges.push(`Rating ≥ ${filters.min_rating}`);
  if (badges.length === 0) return null;

  return (
    <div className="filter-badges">
      <span className="filter-label">Filters applied:</span>
      {badges.map((b) => (
        <span key={b} className="badge">{b}</span>
      ))}
    </div>
  );
}

function WatchProviders({ options, watchLink }) {
  if (!options || options.length === 0) {
    return (
      <p className="modal-line no-providers">
        No streaming info available for India right now.
      </p>
    );
  }

  // Group by type so "Stream" / "Rent" / "Buy" each get their own row
  const grouped = options.reduce((acc, opt) => {
    acc[opt.type] = acc[opt.type] || [];
    acc[opt.type].push(opt);
    return acc;
  }, {});

  return (
    <div className="watch-providers">
      {Object.entries(grouped).map(([type, providers]) => (
        <div key={type} className="provider-row">
          <span className="provider-type">{type}:</span>
          <div className="provider-logos">
            {providers.map((p) => (
              <a
                key={p.provider_name}
                href={watchLink}
                target="_blank"
                rel="noopener noreferrer"
                title={p.provider_name}
              >
                {p.logo_path ? (
                  <img
                    src={`${TMDB_LOGO_BASE}${p.logo_path}`}
                    alt={p.provider_name}
                    className="provider-logo"
                  />
                ) : (
                  <span className="provider-text">{p.provider_name}</span>
                )}
              </a>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function MovieModal({ movieId, onClose }) {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useState(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    axios
      .get(`http://127.0.0.1:8000/movie/${movieId}`)
      .then((res) => {
        if (!cancelled) setDetails(res.data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [movieId]);

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div className="modal-backdrop" onClick={handleBackdropClick}>
      <div className="modal-content">
        <button className="modal-close" onClick={onClose}>✕</button>

        {loading && <div className="modal-loading">Loading details...</div>}
        {error && <div className="modal-loading">Couldn't load details for this movie.</div>}

        {details && !loading && !error && (
          <>
            <div className="modal-body">
              {details.poster_path ? (
                <img
                  src={`${TMDB_IMAGE_LARGE}${details.poster_path}`}
                  alt={details.title}
                  className="modal-poster"
                />
              ) : (
                <div className="modal-poster no-poster">No Image</div>
              )}

              <div className="modal-details">
                <h2 className="modal-title">{details.title}</h2>
                <div className="modal-meta">
                  <span>{details.release_date ? details.release_date.slice(0, 4) : "N/A"}</span>
                  <span>•</span>
                  <span>{details.runtime ? `${details.runtime} min` : "N/A"}</span>
                  <span>•</span>
                  <span>⭐ {details.vote_average ? details.vote_average.toFixed(1) : "N/A"}</span>
                </div>

                {details.genres && details.genres.length > 0 && (
                  <div className="modal-genres">
                    {details.genres.map((g) => (
                      <span key={g} className="badge">{g}</span>
                    ))}
                  </div>
                )}

                <p className="modal-overview">{details.overview}</p>

                {details.director && (
                  <p className="modal-line"><strong>Director:</strong> {details.director}</p>
                )}

                {details.cast && details.cast.length > 0 && (
                  <p className="modal-line">
                    <strong>Cast:</strong>{" "}
                    {details.cast.map((c) => c.name).join(", ")}
                  </p>
                )}

                <a
                  href={details.tmdb_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="modal-tmdb-link"
                >
                  View on TMDB →
                </a>
              </div>
            </div>

            {details.trailer_key && (
              <div className="modal-section">
                <h3 className="modal-section-title">Trailer</h3>
                <div className="trailer-wrapper">
                  <iframe
                    src={`https://www.youtube.com/embed/${details.trailer_key}`}
                    title="Trailer"
                    frameBorder="0"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
                  />
                </div>
              </div>
            )}

            <div className="modal-section">
              <h3 className="modal-section-title">Where to Watch (India)</h3>
              <WatchProviders options={details.watch_options} watchLink={details.watch_link} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState([
    {
      role: "bot",
      text: "Hi! Tell me movies you liked and I'll recommend similar ones, ask me about a specific movie to see its trailer and where to watch it, or just chat. I'll remember what you've told me as we go.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [likedMovies, setLikedMovies] = useState([]);
  const [selectedMovieId, setSelectedMovieId] = useState(null);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setLoading(true);

    try {
      const response = await axios.post("http://127.0.0.1:8000/chat", {
        message: text,
        known_titles: likedMovies,
      });

      const {
        reply_type,
        text: replyText,
        recommendations,
        total,
        filters_applied,
        not_found,
        known_titles,
        needs_titles,
        lookup_movie_id,
      } = response.data;

      setLikedMovies(known_titles || []);

      // Plain text reply: chitchat, movie trivia, or "no titles yet" message
      if (reply_type === "text") {
        setMessages((prev) => [...prev, { role: "bot", text: replyText }]);
        return;
      }

      // Movie lookup: show a short note and open the detail modal immediately
      if (reply_type === "movie_lookup") {
        setMessages((prev) => [...prev, { role: "bot", text: replyText }]);
        setSelectedMovieId(lookup_movie_id);
        return;
      }

      // Otherwise: recommendations flow (existing behavior)
      let botText = "";
      if (not_found && not_found.length > 0) {
        botText += `Couldn't find: ${not_found.join(", ")}. `;
      }

      if (total === 0) {
        botText += "No movies matched. Try broadening your filters!";
        setMessages((prev) => [...prev, { role: "bot", text: botText }]);
      } else {
        const basis = known_titles && known_titles.length > 0
          ? ` based on ${known_titles.join(", ")}`
          : "";
        botText += `Here are ${total} recommendation${total > 1 ? "s" : ""}${basis}:`;
        setMessages((prev) => [
          ...prev,
          {
            role: "bot",
            text: botText,
            movies: recommendations,
            filters: filters_applied,
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: "Something went wrong. Make sure the backend is running on port 8000." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const resetConversation = () => {
    setLikedMovies([]);
    setMessages([
      {
        role: "bot",
        text: "Started fresh! Tell me movies you liked, ask about a specific movie, or just say hi.",
      },
    ]);
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-top">
          <div>
            <h1>🎬 Movie Recommender</h1>
            <p>Tell me what you liked — I'll find what to watch next.</p>
          </div>
          {likedMovies.length > 0 && (
            <button className="reset-btn" onClick={resetConversation}>
              Start Over
            </button>
          )}
        </div>
        {likedMovies.length > 0 && (
          <div className="liked-tracker">
            <span className="liked-label">Remembering you liked:</span>
            {likedMovies.map((t) => (
              <span key={t} className="liked-chip">{t}</span>
            ))}
          </div>
        )}
      </header>

      <div className="chat-window">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="bubble">{msg.text}</div>
            {msg.filters && <FilterBadges filters={msg.filters} />}
            {msg.movies && (
              <div className="movie-grid">
                {msg.movies.map((m) => (
                  <MovieCard key={m.id} movie={m} onClick={setSelectedMovieId} />
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="message bot">
            <div className="bubble loading">Thinking<span className="dots">...</span></div>
          </div>
        )}
      </div>

      <div className="input-area">
        <textarea
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder='Try: "RRR" or "I liked Inception" or "hi"'
          rows={2}
        />
        <button className="send-btn" onClick={sendMessage} disabled={loading}>
          {loading ? "..." : "Send"}
        </button>
      </div>

      {selectedMovieId && (
        <MovieModal
          movieId={selectedMovieId}
          onClose={() => setSelectedMovieId(null)}
        />
      )}
    </div>
  );
}
