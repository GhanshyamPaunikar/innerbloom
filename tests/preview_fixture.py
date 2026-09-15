"""Temporary fictional data for UI review. Never reads the user's data directory."""
import atexit
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta


def configure_demo():
    folder = tempfile.mkdtemp(prefix="innerbloom-design-preview-")
    os.environ["INNERBLOOM_DATA_DIR"] = folder
    os.environ["INNERBLOOM_DEMO"] = "1"
    os.environ["INNERBLOOM_MODEL"] = "Design preview (simulated)"
    atexit.register(shutil.rmtree, folder, ignore_errors=True)
    samples = [
        ("The things I want to keep", "Today felt quieter than usual. I took the longer walk home and let myself notice the things I normally pass by.\n\nI want to remember that feeling. Not everything needs to become something. Some moments can simply be enough.", "calm", ["making space", "time outside", "attention"]),
        ("The long way home", "A slower path, a clearer mind. The longer walk brought the best bits of the day into focus. I left my phone in my pocket and watched the light change.", "grateful", ["time outside", "making space", "rest"]),
        ("Making space", "Cleared a corner, opened a window, and felt a bit more like myself again. Not everything has to be filled. I made room for a morning without a plan.", "reflective", ["making space", "rest", "attention"]),
        ("A little less noise", "Turned down the volume, in every sense. More quiet today, and it made room for what matters. An hour of focused work felt better than a busy afternoon.", "calm", ["meaningful work", "making space", "focus"]),
        ("Finding a rhythm", "Some days work comes naturally; other days I need to start small. Finishing one thing helped me find a rhythm today.", "hopeful", ["meaningful work", "focus", "growth"]),
        ("An honest pause", "I noticed how often I reach for the next task before giving myself a moment. Today I paused, went outside, and returned with a clearer idea of what needed my attention.", "reflective", ["time outside", "attention", "rest"]),
    ]
    entries=[]
    for i in range(30):
        if i in (7,19,25):
            continue
        title, text, emotion, tags = samples[i % len(samples)]
        entries.append({"id":f"demo-{i:03}","timestamp":(datetime.now()-timedelta(days=i)).replace(hour=14,minute=32,second=0,microsecond=0).isoformat(),"title":title,"text":text,"emotion":emotion,"intensity":[4,3,5,6,7,6,4,3,5,6][i%10],"summary":text.split('.')[0]+'.',"tags":tags,"themes":tags[:2],"people":[["Sam"],["Mom"],[],["Sam","Priya"],[],["Mom"]][i%6],"word_count":len(text.split())})
    with open(os.path.join(folder,"journal.json"),"w") as f:json.dump(entries,f)
    import app as backend

    def fake_llama(prompt, system="", temperature=.7, timeout=180, **kwargs):
        if "Return ONLY a compact JSON object" in prompt:
            return json.dumps({"emotion":"reflective","intensity":4,"summary":"A moment of reflection.","tags":["making space","attention"],"themes":["personal growth"]})
        if "journaling prompt" in prompt.lower() or "one short" in prompt.lower():
            return "What made today feel like yours?"
        if "exactly 3 thoughtful" in prompt:
            return "What would you like to remember?\nWhat helped you slow down?\nWhat could you make room for tomorrow?"
        return "**A little more space.**\nYour sample pages often return to slower mornings, meaningful work, and time outside.\n\n**A thought to explore.**\nWhich small practice would you like to carry into tomorrow?\n\nThis is a simulated response in the design preview."

    def fake_stream(*args, **kwargs):
        yield "Looking through these sample pages, a recurring thread is making room for rest and attention. "
        yield "The entry about taking the long way home is one example [cite:demo-001]. "
        yield "What would making a little more space look like tomorrow? (Simulated design-preview response.)"

    backend.embed=lambda text: None
    backend.call_llama=fake_llama
    backend.call_llama_stream=fake_stream
    # Avoid model discovery and network traffic in design preview.
    for route in backend.app.routes:
        if getattr(route,"path",None)=="/health":
            route.endpoint=lambda:{"ollama":"down","demo":True}
            route.dependant.call=route.endpoint
    return backend.app
