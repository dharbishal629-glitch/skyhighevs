import { Switch, Route, Router as WouterRouter, Redirect } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { Layout } from "@/components/layout";
import Dashboard from "@/pages/dashboard";
import Workers from "@/pages/workers";
import Tokens from "@/pages/tokens";
import Leaderboard from "@/pages/leaderboard";
import Analytics from "@/pages/analytics";
import Settings from "@/pages/settings";
import ToolConfig from "@/pages/tool-config";
import ToolFile from "@/pages/tool-file";
import Environment from "@/pages/environment";
import WorkerLogin from "@/pages/worker-login";
import WorkerPortal from "@/pages/worker-portal";
import Login from "@/pages/login";
import NotFound from "@/pages/not-found";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function ProtectedRoute({ component: Component }: { component: React.ComponentType }) {
  const { isAuthenticated, authReady } = useAuth();
  if (!authReady) return null;
  if (!isAuthenticated) return <Redirect to="/login" />;
  return (
    <Layout>
      <Component />
    </Layout>
  );
}

function AppContent() {
  const { isAuthenticated, authReady } = useAuth();

  if (!authReady) {
    return (
      <div className="flex items-center justify-center w-screen" style={{ height: "100dvh", background: "hsl(228 30% 7%)" }}>
        <div style={{ width: 32, height: 32, border: "2px solid rgba(139,92,246,0.3)", borderTopColor: "#8b5cf6", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <Switch>
      <Route path="/login">
        {isAuthenticated ? <Redirect to="/" /> : <Login />}
      </Route>
      <Route path="/" component={() => <ProtectedRoute component={Dashboard} />} />
      <Route path="/workers" component={() => <ProtectedRoute component={Workers} />} />
      <Route path="/tokens" component={() => <ProtectedRoute component={Tokens} />} />
      <Route path="/leaderboard" component={() => <ProtectedRoute component={Leaderboard} />} />
      <Route path="/analytics" component={() => <ProtectedRoute component={Analytics} />} />
      <Route path="/tool-config" component={() => <ProtectedRoute component={ToolConfig} />} />
      <Route path="/tool-file" component={() => <ProtectedRoute component={ToolFile} />} />
      <Route path="/environment" component={() => <ProtectedRoute component={Environment} />} />
      <Route path="/settings" component={() => <ProtectedRoute component={Settings} />} />
      <Route path="/worker-login" component={WorkerLogin} />
      <Route path="/worker" component={WorkerPortal} />
      <Route path="/config" component={() => <ProtectedRoute component={Settings} />} />
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider>
          <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
            <AppContent />
          </WouterRouter>
          <Toaster />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
