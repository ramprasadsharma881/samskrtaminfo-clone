function getContentBeforeF(text) {
    // Use string.split() to split the string at "F:"
    const parts = text.split("F:");

    // Check if there is content before "F:"
    if (parts.length > 1) {
        // Return the first part of the array (content before "F:")
        return parts[0].trim();
    } else {
        // If there's no "F:", return the original string
        return text;
    }
}

let numButtons = 16;
const url = "hitopadesha-adhyayana.php";
// Get the URL parameter value (if available)
const paramName = "page";
let pageNum = new URLSearchParams(window.location.search).get(paramName);
if (!pageNum){
    pageNum = 1;
}


for (let i = 0; i < numButtons; i++) {
    // Create the button element
    const button = document.createElement("button");
    button.textContent = `${i + 1}`;
    // Apply styles to the button
    button.style.margin = "0.15em";
    button.classList.add("mini-btn");
    button.id = `btn`+i;
    // Check if button number matches URL parameter
    if (pageNum && parseInt(pageNum) === i + 1) {
        button.disabled = true;
        button.style.background = 'grey';
    }


    // Add event listener (optional)
    button.addEventListener("click", function() {
        
      console.log(`Button ${i + 1} clicked!`);

      const fullUrl = `${url}?page=${i + 1}`;
      // Open the URL in the same tab
        window.location.href = fullUrl;
       
    });
  
    // Append the button to the desired container (optional)
    // Replace with your container element ID or selector
    document.getElementById("paginationButtons").appendChild(button);
  }

fetch("../xml/adhyayanam.xml")
    .then((response) => response.text())
    .then((text) => {

        const parser = new DOMParser();
        const doc = parser.parseFromString(text, "text/xml");
        const outputElement = document.getElementById("output");
        // Assuming your XML has a root element called "group"
        const groupElements = doc.getElementsByTagName("group");
        //This pageNum value will change based on the page number clicked on the screen.
        //let pageNum = 1;
        let itemsPerPage = 100;
        let startNum = 0 + ((pageNum - 1) * itemsPerPage);
        let endNum = itemsPerPage + ((pageNum - 1) * itemsPerPage);


        for (let i = startNum; i < endNum; i++) {

            const group = groupElements[i];
            const slokatype = group.getAttribute("type");
            let f = group.querySelector("F").textContent;
            // const pattern = /\d+([^:]*)F:/g;
            // f = f.trimStart().replace(/\n/g, ' ').replace(pattern, "");
            const a = group.querySelector("A").textContent;
            const p = group.querySelector("P").textContent;
            const c = group.querySelector("C").textContent;
            const e = group.querySelector("E").textContent;

            //console.log(`group ${i + 1}: F: ${f}, A: ${a}`);
            let fullid;
            let cleanid;
            let audioid;
            if (slokatype === 'prose') {
                fullid = getContentBeforeF(f.trimStart().replace(/\n/g, ' '));
                cleanid = fullid.replace(".", "");
                audioid = 'Hito-G-' + fullid;
            }
            else {
                fullid = slokatype.replace("shloka ", "").replace(",", ".");
                cleanid = fullid.replace(".", "");
                audioid = 'Hito-Sh-' + fullid;
            }


            outputElement.innerHTML += `
    <div class="row sanskrit">                
    <div class="total" id="${cleanid}">
        <div>
            <button id="moolamsmall${cleanid}" class="mini-btn" style="margin:0.2em" onclick="toggleOneSloka(\'moolam\', \'${cleanid}\')">मूलम्</button>
            <button id="padasmall${cleanid}" class="mini-btn" style="margin:0.2em" onclick="toggleOneSloka(\'pada\', \'${cleanid}\')">पदविभागः</button>
            <button id="anvayasmall${cleanid}" class="mini-btn" style="margin:0.2em" onclick="toggleOneSloka(\'anvaya\', \'${cleanid}\')">टिप्पणी</button>
            <button id="pratismall${cleanid}" class="mini-btn" style="margin:0.2em" onclick="toggleOneSloka(\'prati\', \'${cleanid}\')">विश्लेषणम्</button>
            <button id="taatparyamsmall${cleanid}" class="mini-btn" style="margin:0.2em" onclick="toggleOneSloka(\'taatparyam\', \'${cleanid}\')">आङ्ग्लार्थः</button>
            <button id="audiosmall${cleanid}'" class="mini-btn" style="margin:0.2em" onclick="toggleOneSloka(\'audio\', \'${cleanid}\')">उच्चारणम्</button>
        </div>
        <table>
            <tr class="moolam">
                <td style="width: 90px">मूलम् </td>
                <td>${f}</td>
            </tr>
            <tr class="pada">
                <td style="width: 90px">पदविभागः </td>
                <td>${a}</td>
            </tr>
            <tr class="anvaya">
                <td style="width: 90px">टिप्पणी </td>
                <td>${p}</td>
            </tr>
            <tr class="prati">
                <td style="width: 90px">विश्लेषणम् </td>
                <td class="english">${c}</td>
            </tr>
            <tr class="taatparyam">
                <td style="width: 90px">आङ्ग्लार्थः </td>
                <td class="english">${e}</td>
            </tr>
            <tr class="audio">
            <td style="width: 90px">उच्चारणम् </td>
            <td style="vertical-align:bottom">
                <audio controls>
                    <source src="audio/hitopadesa/${audioid}.m4a" type="audio/mp4">
                    Your browser does not support the audio element.
                </audio>
            </td>
        </tr>
        </table>
    </div>
    </div>`
        }

    });


    function gotoTop(){
        $("html, body").animate({
            'scrollTop':   $("#instructions").offset().top
        }, 200);
    }
    gotoTop();

    const spinner = document.getElementById("loading-spinner");

    window.addEventListener("load", function() {
      spinner.style.display = "none";
    });
  
    window.addEventListener("DOMContentLoaded", function() {
      spinner.style.display = "block";
    });