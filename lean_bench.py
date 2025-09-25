#!/usr/bin/env python3
"""
Script to update Lean engine version and run benchmarking or profiling
"""

import argparse
import subprocess
import re
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Union, Dict


def run_command(cmd: List[str], cwd: Optional[Union[str, Path]] = None):
    """Execute a command"""
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, capture_output=False, text=True, check=True)


def run_command_output(cmd: List[str], cwd: Optional[Union[str, Path]] = None) -> str:
    """Execute a command and return output"""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


class GitRepo:
    """Helper class to manage a cloned git repository"""
    def __init__(self, repo_url: str):
        self.temp_dir = tempfile.mkdtemp(prefix="lean-regex-")
        self.repo_url = repo_url
        run_command(["git", "clone", repo_url, self.temp_dir])
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        run_command(["rm", "-rf", self.temp_dir])
    
    def get_recent_branches(self, limit: int = 15) -> List[str]:
        """Get recent branches from the repository"""
        # Get all remote branches
        branches_output = run_command_output(["git", "branch", "-r", "--sort=-committerdate"], cwd=self.temp_dir)
        branches = []
        for line in branches_output.split('\n'):
            line = line.strip()
            if line and not line.startswith('origin/HEAD') and 'origin/' in line:
                branch = line.replace('origin/', '')
                branches.append(branch)
        
        # Ensure main is first if it exists
        if 'main' in branches:
            branches.remove('main')
            branches.insert(0, 'main')
        
        return branches[:limit]
    
    def get_commits_from_branch(self, branch: str, limit: int = 8) -> List[Dict[str, str]]:
        """Get recent commits from a specific branch, stopping at common ancestor with main"""
        if branch == 'main':
            # For main branch, just get recent commits
            commits_output = run_command_output([
                "git", "log", f"origin/{branch}", "--format=%H|%h|%s|%an|%ad", 
                "--date=short", f"-{limit}"
            ], cwd=self.temp_dir)
        else:
            # For non-main branches, stop at common ancestor with main
            try:
                # Find merge base (common ancestor) with main
                merge_base = run_command_output([
                    "git", "merge-base", f"origin/{branch}", "origin/main"
                ], cwd=self.temp_dir)
                
                # Get commits from branch head to merge base (exclusive)
                commits_output = run_command_output([
                    "git", "log", f"origin/{branch}", f"^{merge_base}", 
                    "--format=%H|%h|%s|%an|%ad", "--date=short", f"-{limit}"
                ], cwd=self.temp_dir)
            except subprocess.CalledProcessError:
                # Fallback if merge-base fails
                commits_output = run_command_output([
                    "git", "log", f"origin/{branch}", "--format=%H|%h|%s|%an|%ad", 
                    "--date=short", f"-{limit}"
                ], cwd=self.temp_dir)
        
        commits = []
        for line in commits_output.split('\n'):
            if line and '|' in line:
                parts = line.split('|', 4)
                if len(parts) >= 5:
                    full_hash, short_hash, subject, author, date = parts
                    # Truncate subject to make it concise (one line)
                    subject = subject[:80] + "..." if len(subject) > 80 else subject
                    commits.append({
                        'full_hash': full_hash,
                        'short_hash': short_hash,
                        'subject': subject,
                        'author': author,
                        'date': date,
                        'branch': branch
                    })
        
        return commits
    
    def get_toolchain_info(self, git_rev: str) -> Tuple[str, str, str]:
        """Get toolchain info from regex/lean-toolchain in the cloned repo"""
        # Checkout the specified revision
        run_command(["git", "checkout", git_rev], cwd=self.temp_dir)
        
        # Read the toolchain file
        toolchain_file = os.path.join(self.temp_dir, "regex", "lean-toolchain")
        if not os.path.exists(toolchain_file):
            raise FileNotFoundError(f"lean-toolchain file not found at {toolchain_file}")
        
        with open(toolchain_file, 'r') as f:
            toolchain_line = f.read().strip()
        
        # Extract version from format like "leanprover/lean4:v4.23.0-rc2"
        toolchain_version = toolchain_line.split(":")[-1]
        rev_short = git_rev[:8]
        
        return toolchain_version, git_rev, rev_short
    
    def interactive_commit_selection(self) -> str:
        """Interactively select a commit from recent branches (two-step process)"""
        # Step 1: Select a branch
        print("Fetching recent branches...")
        branches = self.get_recent_branches()
        
        if not branches:
            print("Error: No branches found")
            sys.exit(1)
        
        print("\nAvailable branches:")
        print("=" * 60)
        for i, branch in enumerate(branches, 1):
            print(f"{i:2d}. {branch}")
        
        selected_branch = None
        while True:
            try:
                choice = input(f"\nPlease select a branch (1-{len(branches)}): ").strip()
                if choice == '':
                    continue
                
                index = int(choice) - 1
                if 0 <= index < len(branches):
                    selected_branch = branches[index]
                    print(f"\nSelected branch: {selected_branch}")
                    break
                else:
                    print(f"Error: Please select a number between 1 and {len(branches)}")
            except ValueError:
                print("Error: Please enter a number")
            except KeyboardInterrupt:
                print("\nOperation cancelled")
                sys.exit(1)
        
        # Step 2: Select a commit from the chosen branch
        if selected_branch == 'main':
            print(f"\nFetching recent commits from '{selected_branch}'...")
        else:
            print(f"\nFetching commits from '{selected_branch}' (up to common ancestor with main)...")
        
        commits = self.get_commits_from_branch(selected_branch)
        
        if not commits:
            print(f"Error: No commits found in branch '{selected_branch}'")
            sys.exit(1)
        
        print(f"\nAvailable commits from '{selected_branch}':")
        print("=" * 80)
        for i, commit in enumerate(commits, 1):
            print(f"{i:2d}. {commit['short_hash']} - {commit['subject']}, {commit['author']} ({commit['date']})")
        
        while True:
            try:
                choice = input(f"\nPlease select a commit (1-{len(commits)}): ").strip()
                if choice == '':
                    continue
                
                index = int(choice) - 1
                if 0 <= index < len(commits):
                    selected_commit = commits[index]
                    print(f"\nSelected commit: {selected_commit['short_hash']} - {selected_commit['subject']}")
                    print(f"From branch: {selected_branch}")
                    return selected_commit['full_hash']
                else:
                    print(f"Error: Please select a number between 1 and {len(commits)}")
            except ValueError:
                print("Error: Please enter a number")
            except KeyboardInterrupt:
                print("\nOperation cancelled")
                sys.exit(1)


def update_lean_toolchain(toolchain_file: Union[str, Path], toolchain_version: str) -> None:
    """Update lean-toolchain file"""
    content = f"leanprover/lean4:{toolchain_version}\n"
    with open(toolchain_file, 'w') as f:
        f.write(content)
    print(f"Updated: {toolchain_file}")


def update_lakefile_toml(lakefile_path: Union[str, Path], rev_full: str) -> None:
    """Update revision in lakefile.toml"""
    with open(lakefile_path, 'r') as f:
        content = f.read()
    
    # Update the rev line
    pattern = r'rev = "[^"]*"'
    replacement = f'rev = "{rev_full}"'
    updated_content = re.sub(pattern, replacement, content)
    
    with open(lakefile_path, 'w') as f:
        f.write(updated_content)
    print(f"Updated: {lakefile_path}")


def update_main_lean(main_lean_path: Union[str, Path], toolchain_version: str, rev_short: str) -> None:
    """Update version string in Main.lean"""
    with open(main_lean_path, 'r') as f:
        content = f.read()
    
    # Update version string
    pattern = r'IO\.println "v[^"]*"'
    replacement = f'IO.println "{toolchain_version} ({rev_short})"'
    updated_content = re.sub(pattern, replacement, content)
    
    with open(main_lean_path, 'w') as f:
        f.write(updated_content)
    print(f"Updated: {main_lean_path}")


def get_toolchain_from_files(repo_dir: Path) -> Tuple[str, str]:
    """Get toolchain version and rev_short from existing files"""
    # Read toolchain version from lean-toolchain file
    lean_toolchain_path = repo_dir / "engines" / "lean" / "lean-toolchain"
    with open(lean_toolchain_path, 'r') as f:
        toolchain_line = f.read().strip()
    toolchain_version = toolchain_line.split(":")[-1]
    
    # Read Main.lean to extract rev_short from version string
    main_lean_path = repo_dir / "engines" / "lean" / "Main.lean"
    with open(main_lean_path, 'r') as f:
        content = f.read()
    
    # Extract rev_short from pattern like 'IO.println "v4.23.0-rc2 (12345678)"'
    pattern = r'IO\.println "([^"]*) \(([^)]*)\)"'
    match = re.search(pattern, content)
    if match:
        rev_short = match.group(2)
    else:
        raise ValueError("Could not extract rev_short from Main.lean")
    
    return toolchain_version, rev_short


def build_lean_engine(repo_dir: Path) -> None:
    """Build Lean engine"""
    run_command(["rebar", "build", "-e", "^lean$"], cwd=repo_dir)


def run_benchmarking(repo_dir: Path, engine_filter: str, benchmark_filter: str) -> None:
    """Run benchmarking mode"""
    # Get toolchain info from existing files
    toolchain_version, rev_short = get_toolchain_from_files(repo_dir)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_file = f"{date_str}-{toolchain_version}-{rev_short}.csv"
    
    cmd = ["rebar", "measure", "-e", engine_filter, "-f", benchmark_filter]
    
    print(f"Running benchmark: {' '.join(cmd)}")
    print(f"Output file: {output_file}")
    
    with open(os.path.join(repo_dir, output_file), 'w') as f:
        process = subprocess.Popen(cmd, cwd=repo_dir, stdout=subprocess.PIPE, text=True)
        if process.stdout:
            for line in process.stdout:
                print(line, end='')  # Display to stdout
                f.write(line)        # Write to file
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)


def run_profiling(repo_dir: Path, klv_args: str) -> None:
    """Run profiling mode"""
    # Get toolchain info from existing files
    toolchain_version, rev_short = get_toolchain_from_files(repo_dir)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_file = f"{date_str}-{toolchain_version}-{rev_short}.json.gz"
    
    klv_cmd = ["rebar", "klv"] + klv_args.split()
    samply_cmd = ["samply", "record", "-o", output_file, "./engines/lean/.lake/build/bin/lean_runner"]
    
    print(f"Running profile: {' '.join(klv_cmd)} | {' '.join(samply_cmd)}")
    
    # Connect with pipe
    klv_process = subprocess.Popen(klv_cmd, cwd=repo_dir, stdout=subprocess.PIPE)
    samply_process = subprocess.Popen(samply_cmd, cwd=repo_dir, stdin=klv_process.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if klv_process.stdout:
        klv_process.stdout.close()  # Allow samply_process to receive EOF
    _, stderr = samply_process.communicate()
    
    if samply_process.returncode != 0:
        print(f"Error: {stderr.decode()}")
        raise subprocess.CalledProcessError(samply_process.returncode, samply_cmd)
    
    print(f"Profile complete: {output_file}")


def update_toolchain(repo_dir: Path, toolchain_version: str, git_rev: str, rev_short: str) -> None:
    """Update toolchain files only without building or running"""
    # File paths
    lean_toolchain_path = repo_dir / "engines" / "lean" / "lean-toolchain"
    lakefile_path = repo_dir / "engines" / "lean" / "lakefile.toml"
    main_lean_path = repo_dir / "engines" / "lean" / "Main.lean"
    
    # Check file existence
    for path in [lean_toolchain_path, lakefile_path, main_lean_path]:
        if not path.exists():
            print(f"Error: {path} not found")
            sys.exit(1)
    
    # Update files
    update_lean_toolchain(lean_toolchain_path, toolchain_version)
    update_lakefile_toml(lakefile_path, git_rev)
    update_main_lean(main_lean_path, toolchain_version, rev_short)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update Lean engine version and run benchmarking or profiling")
    parser.add_argument("--git-rev", help="Git revision from pandaman64/lean-regex repo (if not provided in --update mode, will show interactive selection)")
    parser.add_argument("--repo-url", default="https://github.com/pandaman64/lean-regex", help="lean-regex repository URL")
    parser.add_argument("--repo-dir", default=".", help="rebar repository directory")
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--update", action="store_true", help="Update toolchain and build engine")
    mode_group.add_argument("--benchmark", action="store_true", help="Run benchmarking")
    mode_group.add_argument("--profile", action="store_true", help="Run profiling")
    
    # Benchmarking options
    parser.add_argument("--engine-filter", default="^lean$", help="Engine filter (default: ^lean$)")
    parser.add_argument("--benchmark-filter", default="^curated", help="Benchmark filter (default: ^curated)")
    
    # Profiling options
    parser.add_argument("--klv-args", help="klv command arguments for profiling")
    
    args = parser.parse_args()
    
    repo_dir = Path(args.repo_dir).resolve()
    
    try:
        # Mode execution
        if args.update:
            # Use single clone for both interactive selection and toolchain info
            with GitRepo(args.repo_url) as repo:
                # Handle git-rev for update mode
                if not args.git_rev:
                    # Interactive commit selection
                    args.git_rev = repo.interactive_commit_selection()
                
                # Get toolchain info from the same cloned repo
                print(f"Getting toolchain info for git revision: {args.git_rev}")
                toolchain_version, git_rev, rev_short = repo.get_toolchain_info(args.git_rev)
                
                print(f"Toolchain version: {toolchain_version}")
                print(f"Git revision: {git_rev} (short: {rev_short})")
            
            print("\nUpdating toolchain files...")
            update_toolchain(repo_dir, toolchain_version, git_rev, rev_short)
            
            print("\nBuilding Lean engine...")
            build_lean_engine(repo_dir)
            print("Toolchain update and build completed!")
        elif args.benchmark:
            print("\nRunning benchmarking mode...")
            run_benchmarking(repo_dir, args.engine_filter, args.benchmark_filter)
            print("Benchmarking completed!")
        elif args.profile:
            if not args.klv_args:
                print("Error: Profiling mode requires --klv-args")
                sys.exit(1)
            
            print("\nRunning profiling mode...")
            run_profiling(repo_dir, args.klv_args)
            print("Profiling completed!")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
