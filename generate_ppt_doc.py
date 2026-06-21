from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

def create_presentation_doc():
    doc = Document()
    
    # Title
    title = doc.add_heading('ATVED - Presentation Storyboard', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph("This document contains the exact script, bullet points, and visual suggestions for a 8-slide, story-driven presentation of the ATVED project.\n")
    
    # SLIDE 1
    doc.add_heading('Slide 1: The Hook (The Crisis on Our Roads)', level=1)
    doc.add_paragraph('Visual Suggestion: A split screen. On the left, chaotic traffic with multiple ongoing violations (someone without a helmet, triple riding). On the right, a grim statistic about road accidents.')
    doc.add_heading('Bullet Points:', level=2)
    doc.add_paragraph('• The sheer volume of vehicles on our roads has made manual traffic enforcement impossible.', style='List Bullet')
    doc.add_paragraph('• Human police officers cannot be everywhere at once.', style='List Bullet')
    doc.add_paragraph('• The result: rampant violations, lack of accountability, and unsafe streets.', style='List Bullet')
    doc.add_heading('Presenter Script:', level=2)
    p = doc.add_paragraph()
    p.add_run('"Every single day, we witness chaos on our roads. People riding without helmets, three people squeezed onto a single motorcycle, and cars speeding through red lights. The problem isn\'t that we don\'t have rules; the problem is that enforcing them manually at this scale is humanly impossible. We need a system that doesn\'t sleep, doesn\'t blink, and holds everyone accountable."').italic = True
    
    # SLIDE 2
    doc.add_heading('Slide 2: The Problem (Why current systems fail)', level=1)
    doc.add_paragraph('Visual Suggestion: A picture of a traditional, blurry CCTV camera feed next to a massive pile of paper tickets.')
    doc.add_heading('Bullet Points:', level=2)
    doc.add_paragraph('• Traditional CCTVs are "dumb"—they only record video for humans to watch later.', style='List Bullet')
    doc.add_paragraph('• Current speed cameras use expensive, single-purpose radar hardware.', style='List Bullet')
    doc.add_paragraph('• No unified system exists to catch complex human behaviours (like seatbelts or tripling).', style='List Bullet')
    doc.add_heading('Presenter Script:', level=2)
    p = doc.add_paragraph()
    p.add_run('"You might be thinking, \'Don\'t we already have cameras?\' We do. But traditional CCTVs are dumb. They just record video. Someone still has to sit and watch hours of footage to spot a violation. And those expensive speed cameras? They only do one thing: detect speed using expensive radar. There is no single, unified system that can look at a live street and understand complex human behaviors... until now."').italic = True

    # SLIDE 3
    doc.add_heading('Slide 3: The Hero (Introducing ATVED)', level=1)
    doc.add_paragraph('Visual Suggestion: The sleek ATVED logo or the clean architecture workflow diagram we generated earlier.')
    doc.add_heading('Bullet Points:', level=2)
    doc.add_paragraph('• ATVED: Automated Traffic Violation Enforcement & Detection.', style='List Bullet')
    doc.add_paragraph('• Converts any standard, cheap CCTV camera into an intelligent AI agent.', style='List Bullet')
    doc.add_paragraph('• A software-first solution that requires zero expensive hardware upgrades.', style='List Bullet')
    doc.add_heading('Presenter Script:', level=2)
    p = doc.add_paragraph()
    p.add_run('"Enter ATVED: Automated Traffic Violation Enforcement & Detection. We asked ourselves: what if we could take the cheapest, standard CCTV camera on the street, and give it a brain? ATVED is a software-first solution. It takes a normal video feed and runs it through a state-of-the-art AI engine in real-time, instantly transforming any street corner into a fully automated enforcement zone."').italic = True

    # SLIDE 4
    doc.add_heading('Slide 4: The Brains (The AI Triple-Model Architecture)', level=1)
    doc.add_paragraph('Visual Suggestion: A screenshot of the AI tracking bounding boxes (cars, helmets, seatbelts) on a live video feed.')
    doc.add_heading('Bullet Points:', level=2)
    doc.add_paragraph('• Base Model: Tracks the vehicles, calculating mathematical speed over time.', style='List Bullet')
    doc.add_paragraph('• Helmet Model: Scans riders specifically for safety gear.', style='List Bullet')
    doc.add_paragraph('• Seatbelt Model: Pierces through windshields to check for seatbelts.', style='List Bullet')
    doc.add_heading('Presenter Script:', level=2)
    p = doc.add_paragraph()
    p.add_run('"How do we do it? We don\'t just use one AI. We use a highly advanced Triple-Model Architecture. Think of it like a team of virtual police officers watching the same video. One officer tracks the vehicles and mathematically calculates their speed. The second officer specifically looks for helmets and triple riding. The third officer looks through windshields for seatbelts. They merge their data instantly to form a complete picture of the scene."').italic = True

    # SLIDE 5
    doc.add_heading('Slide 5: The Math (The Mathematical Rule Engine)', level=1)
    doc.add_paragraph('Visual Suggestion: A simple flowchart: AI Detections -> Rule Engine -> Violation Trigger.')
    doc.add_heading('Bullet Points:', level=2)
    doc.add_paragraph('• The AI provides the "eyes", but our Rule Engine provides the "logic".', style='List Bullet')
    doc.add_paragraph('• Example: Checks if an AI "person" box overlaps a "motorcycle" box without a "helmet" box.', style='List Bullet')
    doc.add_paragraph('• Ensures >75% confidence to absolutely eliminate false tickets.', style='List Bullet')
    doc.add_heading('Presenter Script:', level=2)
    p = doc.add_paragraph()
    p.add_run('"But seeing isn\'t enough; the system has to understand. That\'s where our Mathematical Rule Engine comes in. The AI provides the \'eyes\', but the Rule Engine is the \'lawyer\'. It takes the raw bounding boxes and applies logic. For example, it calculates the overlap between a motorcycle and a rider. If it counts 3 riders on one bike, or a head with no helmet for multiple frames, it strikes. And it requires 75% confidence or higher, ensuring we never issue a false ticket."').italic = True

    # SLIDE 6
    doc.add_heading('Slide 6: The Action (The E-Challan Pipeline)', level=1)
    doc.add_paragraph('Visual Suggestion: A diagram showing the Camera -> Server -> RTO Database -> SMS Notification.')
    doc.add_heading('Bullet Points:', level=2)
    doc.add_paragraph('• When a violation is triggered, it captures the license plate.', style='List Bullet')
    doc.add_paragraph('• Queries the National RTO Database instantly.', style='List Bullet')
    doc.add_paragraph('• Deducts a digital "Driver Score" and automatically fires an SMS E-Challan.', style='List Bullet')
    doc.add_heading('Presenter Script:', level=2)
    p = doc.add_paragraph()
    p.add_run('"Once the Rule Engine flags a violation, the automated pipeline takes over. It scans the license plate, reaches into our mocked National RTO database, identifies the vehicle owner, and instantly issues an E-Challan. Not only that, but it deducts points from their digital \'Driver Score\', and fires off an automated SMS notification to their mobile phone. It happens in less than a second."').italic = True

    # SLIDE 7
    doc.add_heading('Slide 7: The Command Center (Live Dashboards)', level=1)
    doc.add_paragraph('Visual Suggestion: A screenshot of the dark-mode Police Web Dashboard we built.')
    doc.add_heading('Bullet Points:', level=2)
    doc.add_paragraph('• Beautiful, real-time web interface built for traffic authorities.', style='List Bullet')
    doc.add_paragraph('• Live analytics, recent violations, and individual driver lookup.', style='List Bullet')
    doc.add_paragraph('• Eliminates paperwork and modernizes traffic management.', style='List Bullet')
    doc.add_heading('Presenter Script:', level=2)
    p = doc.add_paragraph()
    p.add_run('"All of this data flows into a beautiful, real-time command center. We built a premium web dashboard where traffic authorities can watch violations roll in live, view analytics, and lookup individual driver scores. It eliminates the mountain of paper tickets and brings traffic enforcement into the 21st century."').italic = True

    # SLIDE 8
    doc.add_heading('Slide 8: The Vision (Safer Streets for Tomorrow)', level=1)
    doc.add_paragraph('Visual Suggestion: A clean, orderly street, or the ATVED logo with a strong closing tagline.')
    doc.add_heading('Bullet Points:', level=2)
    doc.add_paragraph('• Scalable to thousands of cameras nationwide.', style='List Bullet')
    doc.add_paragraph('• Creates a psychological deterrent: drivers know they are being watched.', style='List Bullet')
    doc.add_paragraph('• Ultimate Goal: Saving lives through total accountability.', style='List Bullet')
    doc.add_heading('Presenter Script:', level=2)
    p = doc.add_paragraph()
    p.add_run('"ATVED isn\'t just a piece of software; it\'s a vision for the future of our cities. By making enforcement automated, perfectly accurate, and highly visible, we create a psychological deterrent. When drivers know the system never blinks, behaviors change. Rules are followed. And ultimately, lives are saved. Thank you."').italic = True

    doc.save(r'C:\Users\mahan\OneDrive\Documents\Desktop\Projects\Gridlock_sunny\ATVED_Presentation_Content.docx')
    print("Doc created successfully!")

if __name__ == "__main__":
    create_presentation_doc()
