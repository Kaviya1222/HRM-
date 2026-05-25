import { AuthProvider } from "./store/AuthContext";
import { BrandingProvider } from "./store/BrandingContext";
import AppRouter from "./routes/AppRouter";

function App() {
  return (
    <BrandingProvider>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </BrandingProvider>
  );
}

export default App;
