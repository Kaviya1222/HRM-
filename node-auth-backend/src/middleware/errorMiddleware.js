export function notFoundHandler(req, res) {
  res.status(404).json({ message: "Endpoint not found" });
}

export function errorHandler(err, req, res, next) {
  if (res.headersSent) {
    return next(err);
  }

  const statusCode = err.statusCode || 500;
  const message = statusCode === 500 ? "Server Error" : err.message;
  return res.status(statusCode).json({ message });
}
