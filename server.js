// server.js
require('dotenv').config();
const express = require('express');
const path = require('path');
const mysql = require('mysql2');
const app = express();
const PORT = 3000;

// Middleware
app.use(express.json());

app.use(express.static(path.join(__dirname, 'public')));


// Create connection
const db = mysql.createConnection({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,        // your MySQL username
  password: process.env.DB_PASS, // your MySQL password
  database: process.env.DB_NAME   // database name
});

// Connect to database
db.connect(err => {
  if (err) {
    console.error('Database connection failed:', err);
    return;
  }
  console.log('Connected to MySQL database.');
});

app.get('/api/habits', (req, res) => {
  db.query('SELECT * FROM user_happiness', (err, results) => {
    if (err) {
      console.error('Query error:', err);
      return res.status(500).send('Database error');
    }
    res.json(results);
  });
});

app.post('/api/habits', (req, res) => {
  const { good_day } = req.body;

  db.beginTransaction(err => {
    if (err) return res.status(500).json({ success: false, error: err.message });

    const query = 'INSERT INTO user_happiness (is_good_day) VALUES (?)';
    db.query(query, [good_day], (err, result) => {
      if (err) {
        return db.rollback(() => {
          res.status(500).json({ success: false, error: err.message });
        });
      }

      db.commit(err => {
        if (err) {
          return db.rollback(() => {
            res.status(500).json({ success: false, error: err.message });
          });
        }
        res.json({ success: true, entryId: result.insertId });
      });
    });
  });
});


// Start server
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});