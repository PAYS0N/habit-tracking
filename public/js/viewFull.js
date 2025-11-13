window.onload = () => {
    loadData()
}

async function loadData() {
    const dataOutput = document.querySelector('#data-output')
    const data = await fetch('../api/habits')
    const jsonData = await data.json()
    dataOutput.textContent = JSON.stringify(jsonData)
}