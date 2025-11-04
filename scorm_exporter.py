import os
import zipfile

def generate_scorm(course_text: str, output_dir: str = "scorm_package") -> str:
    os.makedirs(output_dir, exist_ok=True)

    # Save index.html
    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(f"<html><body><pre>{course_text}</pre></body></html>")

    # Save imsmanifest.xml
    manifest = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="com.example.ai-course"
    version="1.0"
    xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
    xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
    xmlns:imsss="http://www.imsglobal.org/xsd/imsss"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.imsglobal.org/xsd/imscp_v1p1                 imscp_v1p1.xsd
      http://www.adlnet.org/xsd/adlcp_v1p3                    adlcp_v1p3.xsd
      http://www.imsglobal.org/xsd/imsss                      imsss_v1p0.xsd">

  <organizations default="org1">
    <organization identifier="org1">
      <title>AI Generated Course</title>
      <item identifier="item1" identifierref="resource1" isvisible="true">
        <title>Lesson 1</title>
        <imsss:sequencing>
          <imsss:controlMode flow="true" completionSetByContent="true"/>
          <imsss:objectives>
            <imsss:primaryObjective objectiveID="completion">
              <imsss:minNormalizedMeasure>0.8</imsss:minNormalizedMeasure>
            </imsss:primaryObjective>
          </imsss:objectives>
        </imsss:sequencing>
      </item>
    </organization>
  </organizations>

  <resources>
    <resource identifier="resource1" type="webcontent" adlcp:scormType="sco" href="index.html">
      <file href="index.html"/>
      <adlcp:completionThreshold>0.8</adlcp:completionThreshold>
    </resource>
  </resources>
</manifest>"""

    with open(os.path.join(output_dir, "imsmanifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifest)

    # ✅ FIX: Save .zip INSIDE the course folder with correct name
    zip_name = f"{os.path.basename(output_dir)}.zip"
    zip_path = os.path.join(output_dir, zip_name)

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, output_dir)
                if file != zip_name:
                    zipf.write(full_path, arcname=arcname)

    return zip_path
