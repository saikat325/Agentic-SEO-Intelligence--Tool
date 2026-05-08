#!/usr/bin/env python3
"""
GitHub Repository Intelligence Tool — CLI Interface
Usage:
    python cli.py ingest https://github.com/owner/repo
    python cli.py query <repo_id> "Where is the authentication logic?"
    python cli.py search <repo_id> "database connection"
    python cli.py status <repo_id>
"""
import typer
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from core.ingestion import clone_repository, walk_files, get_repo_id
from core.chunker import chunk_file
from core.vectorstore import index_chunks, semantic_search, repo_is_indexed
from agents.search_agent import run_query

app = typer.Typer(help="GitHub Repository Intelligence Tool")
console = Console()


@app.command()
def ingest(github_url: str = typer.Argument(..., help="GitHub repository URL")):
    """Clone and index a GitHub repository."""
    console.print(f"\n[bold cyan]🔍 Ingesting:[/bold cyan] {github_url}\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Cloning repository...", total=None)
        meta = clone_repository(github_url)
        repo_id = meta["repo_id"]
        progress.update(task, description=f"Cloned [{meta['status']}] → {meta['owner']}/{meta['repo']}")

        progress.update(task, description="Walking files...")
        files = walk_files(meta["clone_path"])
        progress.update(task, description=f"Found {len(files)} supported files")

        progress.update(task, description="Chunking code...")
        all_chunks = []
        for f in files:
            all_chunks.extend(chunk_file(f))
        progress.update(task, description=f"Created {len(all_chunks)} chunks")

        progress.update(task, description="Embedding & indexing...")
        count = index_chunks(repo_id, all_chunks)
        progress.update(task, description=f"Indexed {count} chunks into vector store")

    console.print(Panel(
        f"[bold green]✅ Ready![/bold green]\n\n"
        f"Repo ID : [yellow]{repo_id}[/yellow]\n"
        f"Files   : {len(files)}\n"
        f"Chunks  : {count}\n\n"
        f"Run queries with:\n"
        f"  [cyan]python cli.py query {repo_id} \"your question\"[/cyan]",
        title="Ingestion Complete",
        border_style="green",
    ))


@app.command()
def query(
    repo_id: str = typer.Argument(..., help="Repository ID from ingest"),
    question: str = typer.Argument(..., help="Natural language question about the code"),
):
    """Ask a natural language question about the codebase."""
    if not repo_is_indexed(repo_id):
        console.print("[bold red]❌ Repository not indexed. Run `ingest` first.[/bold red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]❓ Query:[/bold cyan] {question}\n")

    with Progress(SpinnerColumn(), TextColumn("Thinking..."), console=console) as p:
        p.add_task("", total=None)
        result = run_query(repo_id, question)

    console.print("\n" + "─" * 70)
    console.print(Markdown(result["answer"]))
    console.print("─" * 70)

    if result.get("results"):
        table = Table(title="Top Matching Code Locations", show_lines=True)
        table.add_column("File", style="cyan", no_wrap=False)
        table.add_column("Lines", style="yellow", width=10)
        table.add_column("Symbol", style="green")
        table.add_column("Score", style="magenta", width=8)

        for r in result["results"][:5]:
            table.add_row(
                r["file_path"],
                f"{r['start_line']}-{r['end_line']}",
                f"{r['symbol_name'] or 'N/A'} ({r['symbol_type'] or 'N/A'})",
                str(r["score"]),
            )
        console.print(table)


@app.command()
def search(
    repo_id: str = typer.Argument(...),
    query_text: str = typer.Argument(...),
    top_k: int = typer.Option(5, "--top-k", "-k"),
):
    """Raw semantic search (no LLM) — fast keyword/concept lookup."""
    if not repo_is_indexed(repo_id):
        console.print("[red]Not indexed.[/red]")
        raise typer.Exit(1)

    hits = semantic_search(repo_id, query_text, top_k=top_k)

    table = Table(title=f"Semantic Search: '{query_text}'", show_lines=True)
    table.add_column("#", width=3)
    table.add_column("File", style="cyan")
    table.add_column("Lines", width=10)
    table.add_column("Symbol", style="green")
    table.add_column("Score", width=8)

    for i, h in enumerate(hits, 1):
        table.add_row(
            str(i),
            h["file_path"],
            f"{h['start_line']}-{h['end_line']}",
            h["symbol_name"] or "N/A",
            str(h["score"]),
        )

    console.print(table)

    for i, h in enumerate(hits[:3], 1):
        console.print(Panel(
            h["text"][:400] + ("..." if len(h["text"]) > 400 else ""),
            title=f"[{i}] {h['file_path']} :: {h['symbol_name'] or 'snippet'} (line {h['start_line']})",
            border_style="blue",
        ))


@app.command()
def status(repo_id: str = typer.Argument(...)):
    """Check if a repository is indexed."""
    indexed = repo_is_indexed(repo_id)
    if indexed:
        console.print(f"[green]✅ Repo [yellow]{repo_id}[/yellow] is indexed and ready.[/green]")
    else:
        console.print(f"[red]❌ Repo [yellow]{repo_id}[/yellow] is NOT indexed.[/red]")


if __name__ == "__main__":
    app()
