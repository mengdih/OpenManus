import streamlit as st
import subprocess
import sys
import os
import tempfile
import time
import re

st.set_page_config(page_title="Manus Agent", layout="wide")
st.title("Manus Agent")

# Initialize conversation history
if 'messages' not in st.session_state:
    st.session_state.messages = []

# Display conversation history
for message in st.session_state.messages:
    if message["role"] == "user":
        st.write(f"**You:** {message['content']}")
    else:
        with st.expander("**Manus Response**", expanded=True):
            for step in message['steps']:
                if step['type'] == 'thought':
                    with st.container(border=True):
                        st.write(f"**🧠 Thinking:** {step['content']}")
                elif step['type'] == 'tool_selection':
                    st.write(f"**🛠️ {step['content']}**")
                elif step['type'] == 'tool_execution':
                    with st.container(border=True):
                        st.write(f"**⚙️ Tool Execution ({step['tool']}):** {step['content']}")
            
            # Show raw logs if available
            if 'raw_logs' in message and message['raw_logs']:
                with st.expander("View Raw Logs", expanded=False):
                    st.code(message['raw_logs'], language="plain")
    st.write("---")

# Input for user prompt
user_input = st.text_area("Enter your prompt:", height=100)

# Submit button
if st.button("Submit") and user_input and not user_input.isspace():
    # Add user input to conversation
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Status indicator
    status = st.info("Processing your request...")
    
    # Placeholder for live output
    output_container = st.container()
    
    # Get the current working directory
    current_dir = os.getcwd()
    
    # Create a script file that will run your CLI script with the given input
    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.py') as script_file:
        script_file.write(f"""
import os
import sys

# Ensure the current directory is in Python path
sys.path.append('{current_dir}')
os.chdir('{current_dir}')

# Now import your modules
try:
    import asyncio
    from app.agent.manus import Manus
    from app.logger import logger
    
    async def main():
        agent = Manus()
        await agent.run('''{user_input.replace("'", "\\'")}''')
    
    if __name__ == "__main__":
        asyncio.run(main())
except Exception as e:
    print(f"Error importing modules: {{e}}")
    sys.exit(1)
""")
        script_path = script_file.name
    
    # Create a temp file for output
    output_file = tempfile.NamedTemporaryFile('w', delete=False)
    output_path = output_file.name
    output_file.close()
    
    # Run the script and capture output
    process = subprocess.Popen(
        [sys.executable, script_path],
        stdout=open(output_path, 'w'),
        stderr=subprocess.STDOUT,
        cwd=current_dir  # Set the working directory
    )
    
    # Initialize some containers for live display
    with output_container:
        raw_log_expander = st.expander("Raw Logs", expanded=False)
        step_container = st.container()
    
    # Initialize vars for tracking output
    steps = []
    current_step = None
    raw_logs = ""
    
    # Regex patterns for interesting log components
    thought_pattern = re.compile(r"✨ Manus's thoughts: (.*?)(?=\d{4}-\d{2}-\d{2}|\Z)", re.DOTALL)
    tool_selection_pattern = re.compile(r"🛠️ Manus selected (\d+) tools to use")
    tool_execution_pattern = re.compile(r"🔧 Activating tool: '(.*)'...")
    tool_result_pattern = re.compile(r"🎯 Tool '(.*)' completed its mission! Result: (.*?)(?=\d{4}-\d{2}-\d{2}|\Z)", re.DOTALL)
    
    # Monitor the output file and update UI
    while process.poll() is None:  # While process is running
        try:
            with open(output_path, 'r') as f:
                content = f.read()
                if content and content != raw_logs:
                    # Update raw logs
                    raw_logs = content
                    raw_log_expander.code(raw_logs, language="plain")
                    
                    # Process the logs for structured display
                    with step_container:
                        st.empty()  # Clear previous content
                        
                        # Extract thoughts
                        thoughts = thought_pattern.findall(raw_logs)
                        for thought in thoughts:
                            if thought.strip() and thought.strip() != "None":
                                # Check if we already have this thought
                                thought_text = thought.strip()
                                if not any(s['type'] == 'thought' and s['content'] == thought_text for s in steps):
                                    steps.append({
                                        'type': 'thought',
                                        'content': thought_text
                                    })
                        
                        # Extract tool selections
                        tool_selections = tool_selection_pattern.findall(raw_logs)
                        for selection in tool_selections:
                            selection_text = f"Selected {selection} tools"
                            if not any(s['type'] == 'tool_selection' and s['content'] == selection_text for s in steps):
                                steps.append({
                                    'type': 'tool_selection',
                                    'content': selection_text
                                })
                        
                        # Extract tool executions
                        tool_executions = tool_execution_pattern.findall(raw_logs)
                        for tool in tool_executions:
                            if not any(s['type'] == 'tool_execution' and s['tool'] == tool for s in steps):
                                # This is a new tool execution, add it without content yet
                                steps.append({
                                    'type': 'tool_execution',
                                    'tool': tool,
                                    'content': "Executing..."
                                })
                        
                        # Extract tool results
                        tool_results = tool_result_pattern.findall(raw_logs)
                        for tool, result in tool_results:
                            # Update the corresponding tool execution
                            for step in steps:
                                if step['type'] == 'tool_execution' and step['tool'] == tool:
                                    step['content'] = result.strip()
                                    break
                        
                        # Display all steps
                        for step in steps:
                            if step['type'] == 'thought':
                                with st.container(border=True):
                                    st.write(f"**🧠 Thinking:** {step['content']}")
                            elif step['type'] == 'tool_selection':
                                st.write(f"**🛠️ {step['content']}**")
                            elif step['type'] == 'tool_execution':
                                with st.container(border=True):
                                    st.write(f"**⚙️ Tool Execution ({step['tool']}):** {step['content']}")
        except Exception as e:
            st.error(f"Error reading output: {e}")
        
        # Wait a bit before checking again
        time.sleep(0.5)
    
    # Final read of output
    try:
        with open(output_path, 'r') as f:
            final_output = f.read()
            raw_logs = final_output
            raw_log_expander.code(raw_logs, language="plain")
    except Exception as e:
        st.error(f"Error reading final output: {e}")
    
    # Add response to conversation
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "Processed your request",
        "steps": steps,
        "raw_logs": raw_logs
    })
    
    # Clean up temp files
    try:
        os.unlink(script_path)
        os.unlink(output_path)
    except:
        pass
    
    # Clear status and output container
    status.empty()
    output_container.empty()
    
    # Refresh UI
    st.rerun()

# Sidebar with clear button
with st.sidebar:
    st.header("About Manus Agent")
    st.write("""
    **Available Tools:**
    - Python Execution
    - Google Search
    - Web Browsing
    - File Saving
    - Termination
    
    This interface allows you to interact with the Manus agent, 
    a versatile AI assistant that can help with various tasks.
    """)
    
    if st.button("Clear Conversation"):
        st.session_state.messages = []
        st.rerun()