function LoadingScreen({ label = "Loading your workspace…" }) {
  return (
    <div className="loading-screen">
      <div className="loading-screen-card">
        <div className="loading-orb" />
        <p>{label}</p>
      </div>
    </div>
  );
}

export default LoadingScreen;
