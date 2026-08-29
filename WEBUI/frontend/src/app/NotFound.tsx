export function NotFound({ message = "Choose a project to continue." }: { message?: string } = {}) {
  return (
    <main className="empty-state">
      <h1>Page not found</h1>
      <p>{message}</p>
    </main>
  );
}
