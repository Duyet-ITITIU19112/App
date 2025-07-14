document.addEventListener("DOMContentLoaded", function () {
    const searchButton = document.getElementById("searchButton");
    const searchBar = document.getElementById("searchBar");
    const fileList = document.getElementById("fileList");

    // Event listener for the Search button
    searchButton.addEventListener("click", function () {
        const keyword = searchBar.value.trim().toLowerCase();
        if (keyword) {
            searchFiles(keyword); // Perform the search
        } else {
            fileList.innerHTML = "<li>Please enter a keyword to search.</li>";
        }
    });

    // Function to fetch search results from the API
    async function searchFiles(keyword) {
        fileList.innerHTML = "<li>Loading...</li>"; // Show loading message

        try {
            const response = await fetch(`/api/search?keyword=${encodeURIComponent(keyword)}`, {
                method: "GET",
                headers: {
                    "Content-Type": "application/json"
                }
            });

            if (!response.ok) {
                const error = await response.json();
                console.error("Error fetching search results:", error);
                fileList.innerHTML = "<li>Failed to load search results. Please try again.</li>";
                return;
            }

            const data = await response.json();
            const files = data.files;

            fileList.innerHTML = ""; // Clear loading message

            if (files.length === 0) {
                fileList.innerHTML = "<li>No matching files found.</li>";
                return;
            }

            files.forEach(file => {
                const listItem = document.createElement("li");
                listItem.innerHTML = `📄 <span 
                    class="file" 
                    data-url="${file.webUrl}" 
                    data-name="${file.name}" 
                    data-resource-id="${file.id}">
                    ${file.name}
                </span>`;
                fileList.appendChild(listItem);
            });

            attachFileListeners(); // Attach click listeners to the file elements
        } catch (error) {
            console.error("Error fetching files:", error);
            fileList.innerHTML = "<li>Failed to load search results. Please try again.</li>";
        }
    }

    // Attach click event listeners to file elements
    function attachFileListeners() {
        document.querySelectorAll(".file").forEach(fileElement => {
            fileElement.addEventListener("click", function () {
                const fileUrl = this.getAttribute("data-url");
                const fileName = this.getAttribute("data-name");

                const fileExtension = fileName.substring(fileName.lastIndexOf(".")).toLowerCase();

                if (fileExtension === ".pdf") {
                    // Open PDF files directly in a new tab
                    window.open(fileUrl, "_blank");
                } else if ([".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"].includes(fileExtension)) {
                    // Use OneDrive viewer for Office files
                    const viewerUrl = fileUrl; // Assuming webUrl opens directly in OneDrive viewer
                    window.open(viewerUrl, "_blank");
                } else {
                    // Default fallback for unsupported types
                    window.open(fileUrl, "_blank");
                }
            });
        });
    }
});
