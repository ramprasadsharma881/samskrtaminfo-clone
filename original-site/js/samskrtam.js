var counter=0;

function filterSelection(c) {
    //alert("SIVA: It is: "+c);
    var x, i;
    counter = 0;
    x = document.getElementsByClassName("customFilter");
    if (c == "all") c = "";
    for (i = 0; i < x.length; i++) {
        // alert("SIVA: Removing: ");
        w3RemoveClass(x[i], "customShow");

        if (x[i].className.indexOf(c) > -1){
            // alert("SIVA: Adding: ");
            w3AddClass(x[i], "customShow");
        } 

    }
}

function w3AddClass(element, name) {
    var i, arr1, arr2;
    arr1 = element.className.split(" ");
    arr2 = name.split(" ");
    
    for (i = 0; i < arr2.length; i++) {
        if (arr1.indexOf(arr2[i]) == -1) {
            //alert("SIVA: Adding: "+arr2[i]);
            element.className += " " + arr2[i];
        }
    }
}

function w3RemoveClass(element, name) {
    var i, arr1, arr2;
    arr1 = element.className.split(" ");
    arr2 = name.split(" ");
    for (i = 0; i < arr2.length; i++) {
        while (arr1.indexOf(arr2[i]) > -1) {
            arr1.splice(arr1.indexOf(arr2[i]), 1);     
        }
    }
    element.className = arr1.join(" ");
}


function myFunction() {
    var x = document.getElementById("myInput");
    let search = x.value.toLowerCase();
    filterSelection(search);
}