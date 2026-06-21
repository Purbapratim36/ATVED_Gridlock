from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

def create_project_proposal_doc():
    doc = Document()
    
    # Title
    title = doc.add_heading('Automated Photo Identification and Classification for Traffic Violations Using Computer Vision', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 1. Overview
    doc.add_heading('1. Overview', level=1)
    doc.add_paragraph('With the increasing deployment of traffic surveillance cameras and automated monitoring systems, large volumes of traffic images are generated every day. Manual inspection of these images to identify traffic violations is labor-intensive, time-consuming, and prone to inconsistencies. An intelligent system capable of automatically analyzing photographic evidence can significantly improve the efficiency and accuracy of traffic law enforcement.')

    # 2. Objective
    doc.add_heading('2. Objective', level=1)
    doc.add_paragraph('The objective of this project is to develop a computer vision–based solution that can automatically process traffic images, detect vehicles and road users, identify traffic violations, classify the type of violation, and generate annotated evidence for further review. The system is designed to be robust against varying environmental conditions, traffic densities, and image qualities while maintaining high detection accuracy and scalability.')

    # 3. Tasks & Technical Execution Workflow
    doc.add_heading('3. Tasks & Technical Execution Workflow', level=1)
    
    # Task 1
    doc.add_heading('Task 1: Image Preprocessing', level=2)
    doc.add_paragraph('• The system automatically enhances the video feed to handle real-world weather challenges, such as low light, rain, and dark shadows, ensuring clear images for analysis.', style='List Bullet')
    
    # Task 2
    doc.add_heading('Task 2: Vehicle and Road User Detection', level=2)
    doc.add_paragraph('• The AI identifies and draws boxes around all vehicles (cars, trucks, buses), riders, and pedestrians in the camera view.', style='List Bullet')
    doc.add_paragraph('• It tracks these vehicles as they move across the screen to ensure they are only counted once.', style='List Bullet')
    
    # Task 3
    doc.add_heading('Task 3: Traffic Violation Detection', level=2)
    doc.add_paragraph('The system uses smart logic to detect specific rules being broken:', style='List Bullet')
    doc.add_paragraph('  - Helmet Non-compliance & Triple Riding: It counts the number of riders on a motorcycle and checks their heads for safety gear.', style='List Bullet')
    doc.add_paragraph('  - Wrong-side Driving & Stop-line Violation: It watches the direction of traffic and flags vehicles crossing invisible boundaries.', style='List Bullet')
    doc.add_paragraph('  - Red-light Violation: It automatically issues tickets if a vehicle crosses an intersection while the system state is RED.', style='List Bullet')
    
    # Task 4
    doc.add_heading('Task 4: Violation Classification', level=2)
    doc.add_paragraph('• Detected violations are categorized (e.g., "Triple Riding", "Speeding").', style='List Bullet')
    doc.add_paragraph('• The AI assigns a confidence score to its decision. If the AI is not absolutely certain, the event is ignored to prevent false tickets.', style='List Bullet')

    # Task 5
    doc.add_heading('Task 5: License Plate Recognition (ALPR)', level=2)
    doc.add_paragraph('• When a violation is confirmed, the system locates the number plate and reads the text on it to identify the vehicle.', style='List Bullet')

    # Task 6
    doc.add_heading('Task 6: Evidence Generation', level=2)
    doc.add_paragraph('• The system saves an image photograph as visual proof of the violation.', style='List Bullet')
    doc.add_paragraph('• It stores important details like the exact timestamp, location, and the rule that was broken.', style='List Bullet')

    # Task 7
    doc.add_heading('Task 7: Analytics and Reporting', level=2)
    doc.add_paragraph('• All ticket records are securely saved in a database.', style='List Bullet')
    doc.add_paragraph('• A Web Dashboard allows traffic police to search for records, view live tickets, and generate statistical reports.', style='List Bullet')

    # Task 8
    doc.add_heading('Task 8: Performance Evaluation', level=2)
    doc.add_paragraph('• The accuracy and speed of the AI system are continuously measured to ensure it works effectively in real-world traffic.', style='List Bullet')
    
    # 4. Expected Outcome & Future Scope
    doc.add_heading('4. Expected Outcome', level=1)
    doc.add_paragraph('A scalable, AI-based traffic analysis system capable of automatically identifying and documenting traffic violations. This will drastically reduce the need for manual police enforcement and improve overall road safety.')

    doc.add_heading('Future Scope & Current Limitations', level=2)
    doc.add_paragraph('While the software architecture is robust, two specific violation types have been marked for future implementation due to hardware and data constraints:', style='List Bullet')
    
    doc.add_paragraph('1. Seatbelt Non-compliance:', style='List Bullet')
    doc.add_paragraph('Reasoning: Detecting a seatbelt requires the camera to see clearly through a vehicle\'s windshield. In real-world outdoor conditions, windshields produce severe sun glare and reflections that standard CCTV cameras cannot penetrate. Implementing this effectively requires specialized hardware, specifically cameras equipped with Polarizing Lens Filters to cut through reflections, and Infrared (IR) Illuminators to illuminate the driver through the glass. These are planned for future hardware deployment phases.')
    
    doc.add_paragraph('2. Illegal Parking:', style='List Bullet')
    doc.add_paragraph('Reasoning: A vehicle being stationary is not inherently illegal; it depends entirely on the specific location (e.g., bus stops, fire lanes, or no-parking zones). Implementing this requires place-specific GIS details, zoning data, and custom boundary mapping for every individual camera installation. This geographic calibration layer is planned for a future deployment phase.')

    doc.save(r'C:\Users\mahan\OneDrive\Documents\Desktop\Projects\Gridlock_sunny\ATVED_Project_Proposal.docx')
    print("Doc created successfully!")

if __name__ == "__main__":
    create_project_proposal_doc()
