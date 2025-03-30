import time
import dearpygui.dearpygui as dpg
import io
import cProfile
import pstats

# Function to start profiling the code
def run_profiling():
    # Create a StringIO object to capture the profiler output
    pr = cProfile.Profile()
    pr.enable()
    
    # Run some code here that you want to profile
    example_function_to_profile()  # This function will be profiled

    pr.disable()

    # Capture stats into a string
    s = io.StringIO()
    stats = pstats.Stats(pr, stream=s)
    stats.strip_dirs()
    stats.sort_stats("time")
    stats.print_stats()
    
    return s.getvalue()

# Example function to profile
def example_function_to_profile():
    total = 0
    for i in range(1000000):
        total += i
    return total

# Function to update the profiler stats in the GUI when the button is clicked
def on_button_click(sender, app_data):
    stats = run_profiling()  # Get the stats as a stri
    
    dpg.set_value("Profiler Stats", stats)

def create_profiler_window():

    # Setup Dear PyGui context
    dpg.create_context()

    # Create the window to display the profiler stats
    with dpg.window(label="Profiler Stats"):
        dpg.add_text("Profiler Stats will appear here.", tag="Profiler Stats")
        dpg.add_button(label="Run Profiler", callback=on_button_click)

    # Setup Dear PyGui viewport
    dpg.create_viewport(title="Profiler Stats", width=800, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()

    # Start the Dear PyGui event loop
    dpg.start_dearpygui()

    # Cleanup context after closing the window
    dpg.destroy_context()


    # Cleanup context after closing the window
