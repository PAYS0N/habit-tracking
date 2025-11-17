window.onload = () => {
    setupListeners()
}

function setupListeners() {
    document.querySelector('#had-good-day').addEventListener('click', () => {makeApiCall(true)})
    document.querySelector('#had-bad-day').addEventListener('click', () => {makeApiCall(false)})

}

async function makeApiCall(had_good_day) {
    const data = await fetch('../api/habits', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ good_day: had_good_day }),
    })

    const jsonData = await data.json()
    if (jsonData.success === true) {
        console.log("success")
    } 
    else {
        console.log("failure")
    }

}